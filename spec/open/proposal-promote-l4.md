# Proposal: Promote l4-cache-mgmt - flat_vec_cache + O_DIRECT 4T fix {#PROP-PROMOTE-L4}

> track: promote
> Status: Implemented on 2026-08-03
> 日期: 2026-08-03
> Promotes: l4-cache-mgmt
> 关联 TOPIC: `poc/l4-cache-mgmt/ndf/TOPIC.md`
> 关联: [[BEH-024]], [[CHR-006]], [[CON-SLA-014]], [[DEC-067]], [[CON-HONEST-002]]

## 动机

L4 POC 发现两个可 promote 的改进：

### 1. fine rerank 未查 flat_vec_cache（代码 bug）

fine rerank 候选循环中，查 BlockCache 后直接跳到 pread，**没有查 flat_vec_cache**。
flat_vec_cache 是 4MB 进程内热向量缓存（8128 slots），但只在 Phase A 用，fine rerank 没用上。

**影响**：热向量在 fine rerank 时走 pread 读磁盘，即使它们已在 flat_vec_cache 中。
在 page cache 不足的严格隔离场景下（256MB cgroup），这导致大量不必要的 I/O。

**修复**：在候选循环开头加 `if (const float* fv = cache_->getFlatVector(nid)) { consider(nid, fv); continue; }`

### 2. O_DIRECT 4T pread 条件错误（代码 bug）

`if (kFinePread && !kFineDirect)` 条件导致 O_DIRECT 模式跳过 pread 路径，
走了非线程安全的 io_uring 路径。4T 并发时 SQE/CQE 竞争导致 I/O 丢失，recall 崩到 12%。

**修复**：改为 `if (kFinePread)`，buffer 改用 `posix_memalign` 满足 O_DIRECT 对齐。

## 证据

### 256MB cgroup（page cache 不足场景）

| flat_vec | QPS (修复前) | QPS (修复后) | refault | 提升 |
|----------|-------------|-------------|---------|------|
| 4MB (默认) | 126 | 139 | 27666 | +10% |
| 64MB | - | **947** | 4048 | **7.5x** |

### 512MB cgroup（page cache 充裕）

| 配置 | QPS (修复前) | QPS (修复后) | 说明 |
|------|-------------|-------------|------|
| 4MB flat_vec | 2383 | 2326 | -2% (噪声，无回归) |

### O_DIRECT 4T recall 修复

| 配置 | Recall (修复前) | Recall (修复后) |
|------|----------------|----------------|
| O_DIRECT 4T | 12.40% ❌ | 95.75% ✅ |

## 变更清单

### 代码变更（干净合入 src/）

| 文件 | 变更 | 行数 |
|------|------|------|
| `src/core/disk_hnsw.cpp` | fine rerank 候选循环加 `getFlatVector()` 检查 | +2 行 |
| `src/core/disk_hnsw.cpp` | `if (kFinePread && !kFineDirect)` -> `if (kFinePread)` | 1 行改 |
| `src/core/disk_hnsw.cpp` | pread buffer: `new char[]` -> `posix_memalign` | ~3 行改 |

### NDF 变更

| 位置 | ID | 动作 |
|------|-----|------|
| `20-behavior/search.md` | BEH-024 | draft -> stable（L4 主动管理：flat_vec_cache 在 fine rerank 中命中）|
| `decisions/` | DEC-068 | 新增：promote 决策记录 |

### 不变更

- [[CHR-006]] SLA 数字不变（512MB 下无回归）
- [[CON-SLA-011]] 不变
- `FLAT_VEC_MB` 默认值暂不改（4MB），由用户按需调整

## 验证计划

1. **编译验证**（场景5）：`make bench` 通过
2. **性能验证**（场景6）：
   - SIFT1M 512MB cgroup：QPS ≥ 2000 (1T) / ≥ 5000 (4T)，Recall ≥ 95%
   - SIFT1M 256MB cgroup（可选）：QPS ≥ 126 × 1.1（R4 4MB 配置）
   - O_DIRECT 4T：Recall ≥ 95%
3. **无回归**：512MB 下 QPS 不低于基线 × 0.95
