# Proposal: Promote WILLNEED - fine rerank readahead hint {#PROP-PROMOTE-WILLNEED}

> track: promote  
> Status: Implemented on 2026-08-04  
> 日期: 2026-08-04  
> Promotes: l4-cache-mgmt (R5 amendment)  
> 关联 TOPIC: `poc/l4-cache-mgmt/ndf/TOPIC.md`（[[BEH-025]]）  
> 关联: [[BEH-024]](stable), [[CON-SLA-014]], [[DEC-067]], [[DEC-068]], [[CON-HONEST-002]]  
> 依赖提案: `spec/open/proposal-promote-l4.md` (已 Implemented), `poc/l4-cache-mgmt/ndf/proposals/proposal-l4-r5-willneed-selective.md` (已 Implemented)

## 1. 动机

L4 POC R5 发现：在 fine rerank 的 pread 循环前，对 `pages_needed` 中所有页调用
`posix_fadvise(POSIX_FADV_WILLNEED)`，可让内核启动异步 readahead。当 pread 执行时，
页已在 page cache 中，pread 从阻塞磁盘 I/O 变为内存拷贝。

### 核心发现

WILLNEED 的本质是**免费的 I/O 流水线**：不增加内存使用，不减少磁盘 I/O 量，
仅通过改变 I/O 时序（串行 -> 并行）获得性能提升。

| 场景 | page cache 状态 | WILLNEED 效果 | 原因 |
|------|----------------|-------------|------|
| SIFT1M 256MB | 严重不足 | **17.7x QPS** | pread 是瓶颈，readahead 消除串行等待 |
| SIFT1M 512MB | 充裕 | +5.5%（无回归） | pread 非瓶颈，但 readahead 仍有微正 |
| DEEP10M 2GB | 不足 | ~0%（中性） | I/O 量是瓶颈（68K majfault），非时序 |

### 适用条件

WILLNEED 在以下条件同时满足时有效：
1. page cache 严重受限（budget << hot working set）
2. pread 是 query 延迟的主要来源
3. refault 暴涨证明 LRU 在误杀热页

不满足时无副作用（512MB +5.5%，DEEP10M ~0%），因此作为 opt-in 环境变量安全合入。

## 2. 证据（CON-SLA-014 标准协议）

### SIFT1M 256MB cgroup（page cache 不足场景）

| 配置 | QPS | Recall | RSS | refault | majfault | peak | file | max_events | oom |
|------|-----|--------|-----|---------|----------|------|------|------------|-----|
| 基线 | 134 | 95.75% | 153MB | 27718 | 5102 | 256MB | 103MB | 3549 | 0 |
| +WILLNEED | **2379** | 95.75% | 153MB | 74 | 5134 | 256MB | 103MB | 2683 | 0 |

- QPS 17.7x 提升
- refault 27718 -> 74（99.7% 减少）
- majfault 不变（5102 vs 5134）-- I/O 量不减少
- peak=256MB, oom=0 -- cgroup 限制生效，无白嫖

### SIFT1M 512MB cgroup（page cache 充裕，回归验证）

| 配置 | QPS | Recall | RSS | refault | majfault | peak | file |
|------|-----|--------|-----|---------|----------|------|------|
| 基线 | 2267 | 95.75% | 155MB | 0 | 6 | 512MB | 172MB |
| +WILLNEED | 2392 | 95.75% | 155MB | 0 | 6 | 512MB | 130MB |

- QPS +5.5%，无回归 ✅
- Recall/RSS/refault/majfault 全部不变
- file 从 172MB 降到 130MB（WILLNEED 更精准的预取使用更少 page cache）

### DEEP10M 2GB cgroup（10M 规模验证）

| 配置 | QPS | Recall | RSS | refault | majfault | peak | file |
|------|-----|--------|-----|---------|----------|------|------|
| 基线 | 570 | 95.05% | 1157MB | 248 | 68152 | 2GB | 857MB |
| +WILLNEED | 568 | 95.05% | 1156MB | 208 | 68707 | 2GB | 740MB |

- QPS -0.4%（中性，无回归）✅
- pread 延迟降低（21ms -> 12ms）但 QPS 不变（I/O 量是瓶颈）
- cgroup 强制执行：peak=2GB, oom=0

## 3. 代码变更（干净合入 `src/`）

### 3.1 变更内容

| 文件 | 变更 | 行数 |
|------|------|------|
| `src/core/disk_hnsw.cpp` | fine rerank `pages_needed` 填充后、pread/io_uring 分支前，加入 WILLNEED fadvise 循环 | +7 行 |

### 3.2 代码

在 `pages_needed` 填充完成后、`if (kFinePread)` 之前插入：

```cpp
// L4 WILLNEED: hint kernel to prefetch fine rerank pages before reading
static const bool kL4Willneed = std::getenv("L4_WILLNEED") && std::atoi(std::getenv("L4_WILLNEED")) != 0;
if (kL4Willneed && !pages_needed.empty() && vec_blocks_fd_ >= 0) {
    for (uint32_t pg : pages_needed) {
        posix_fadvise(vec_blocks_fd_, (off_t)pg << 12, 4096, POSIX_FADV_WILLNEED);
    }
}
```

### 3.3 不变更

- `L4_WILLNEED` 默认值为 0（opt-in），不影响现有行为
- [[CHR-006]] SLA 数字不变
- [[CON-SLA-014]] 协议不变
- `FLAT_VEC_MB` 默认值不变（4MB）
- 不改 `FINE_FADVISE` / `L4_SELECTIVE_DONTNEED`（后者保持 POC only）

## 4. NDF 变更

### 4.1 条款变更

| 位置 | ID | 动作 |
|------|-----|------|
| `20-behavior/search.md` | [[BEH-024]] | amend：新增 WILLNEED readahead 段落（stable 条款扩展） |

### 4.2 BEH-024 扩展内容

在现有 BEH-024 末尾（rationale 之后）追加：

> **WILLNEED readahead（opt-in）**：当 `L4_WILLNEED=1` 且 Buffered 模式时，
> fine rerank 的 `pages_needed` 填充后 MUST 对每个页调用
> `posix_fadvise(vec_blocks_fd_, offset, 4096, POSIX_FADV_WILLNEED)`，
> 提示内核启动异步 readahead。此机制在 page cache 严重受限场景下
> 可将串行 pread 转为流水线 I/O，QPS 提升可达 17.7x（SIFT1M 256MB cgroup）。
> 在 page cache 充裕或 I/O 量主导场景下无副作用（+5.5% / ~0%）。
> 默认关闭（`L4_WILLNEED=0`）。

### 4.3 接口变更

| 位置 | ID | 动作 |
|------|-----|------|
| `30-interfaces/env.md` | API-012 (新增) | stable：`L4_WILLNEED` 环境变量定义 |

### 4.4 决策记录

| 位置 | ID | 动作 |
|------|-----|------|
| `spec/decisions/` | DEC-070 (新增) | promote 决策记录 |

## 5. 验证计划

### 5.1 编译验证（场景5）

- `make bench` 通过（POC 已编译验证，Trunk 同位置插入）

### 5.2 性能验证（场景6）

对照 [[CON-SLA-014]] + [[CHR-006]] stable SLA：

| 配置 | SLA 要求 | 预期 |
|------|----------|------|
| SIFT1M 512MB 1T, WILLNEED=0 | QPS ≥ 2000, Recall ≥ 95% | ~2267（基线不变） |
| SIFT1M 512MB 1T, WILLNEED=1 | QPS ≥ 2000, Recall ≥ 95% | ~2392（+5.5%，无回归） |
| SIFT1M 512MB 4T, WILLNEED=0 | QPS ≥ 5000, Recall ≥ 95% | 待验证 |
| SIFT1M 512MB 4T, WILLNEED=1 | QPS ≥ 5000, Recall ≥ 95% | 待验证 |

### 5.3 无回归确认

- WILLNEED=0（默认）时行为与代码变更前完全一致
- WILLNEED=1 时在所有测试场景下 Recall 不变（95.75% / 95.05%）
- cgroup 限制始终生效（peak=limit, oom=0）

## 6. 非目标

- 不 promote `L4_SELECTIVE_DONTNEED`（R5b 仅 +14%，场景有限，保持 POC）
- 不改 `FINE_FADVISE` 行为（R1 blanket DONTNEED，保持现状）
- 不改 `FLAT_VEC_MB` 默认值
- 不改 SLA 数字（WILLNEED 是 opt-in 加速，不是 must 要求）
