> Status: Implemented on 2026-07-31
> L1 条款 CON-HONEST-002 已落地到 40-constraints/limits.md

# Proposal: O_DIRECT 诚实基准测试 - Page Cache 水分摸底 {#PROP-ODIRECT-BENCH}

> 关联决策: DEC-030 (O_DIRECT 诊断模式), DEC-039 (诚实协议)
> 关联条款: DEC-009 (Fine Rerank), CHR-003 (SLA)
> 场景: 场景6 (性能验证) + 场景2 (Bug修复 - O_DIRECT pread 对齐)
> 日期: 2026-07-31

## 动机

**核心问题**: DiskHNSW 在 SIFT1M/DEEP10M 的所有性能数字都依赖 OS page cache 做
隐式缓存。cgroup 限制 512MB/2GB，但 page cache 白嫖了 496MB/3.7GB 的 vecblocks 文件。
真实内存使用远超 cgroup 限制。

DEC-039 虽然加了 `drop_caches` + `posix_fadvise(DONTNEED)`，但只解决查询间的
page cache 复用，查询内 I/O 仍经过 page cache。需要 O_DIRECT 彻底绕过 page cache，
测量真实磁盘 I/O 性能。

**本提案回答一个问题**: page cache 消除后，DiskHNSW 的 QPS 到底是多少？

## 已发现问题: O_DIRECT + pread buffer 对齐 bug {#BUG-ALIGN}

### 根因

`FINE_DIRECT=1 FINE_PREAD=1` 组合下，pread 路径使用 `std::make_unique<char[]>(read_bytes)`
分配缓冲区。O_DIRECT 要求缓冲区地址对齐到 512 字节（或 block size），但 `new char[]`
只保证 `alignof(max_align_t)` (通常 16 字节) 对齐，**不满足 O_DIRECT 要求**。

### 影响

- `FINE_DIRECT=1 FINE_PREAD=1` 在运行时会因 `EINVAL` 失败，pread 返回 -1
- 当前无人触发此组合，所以 bug 未暴露
- io_uring 路径已用 `posix_memalign` (line 1858)，对齐正确

### 修复

pread 路径的 buffer 改用 `posix_memalign`：

```cpp
// 修复前 (line 2001):
auto buf = std::make_unique<char[]>(read_bytes);

// 修复后:
char* raw = nullptr;
posix_memalign((void**)&raw, 4096, read_bytes);
auto buf = std::unique_ptr<char, void(*)(char*)>(raw, [](char* p) { free(p); });
```

同理 `page_cache[pg]` 的单页 buffer (line 2007) 也需对齐：
```cpp
// 修复前:
page_cache[pg] = std::make_unique<char[]>(4096);

// 修复后:
char* page_raw = nullptr;
posix_memalign((void**)&page_raw, 4096, 4096);
page_cache[pg] = std::unique_ptr<char, void(*)(char*)>(page_raw, [](char* p) { free(p); });
```

## 实验设计

### 三组对照

| 组 | 配置 | 说明 |
|----|------|------|
| **A. Buffered (不诚实)** | `FINE_BUFFERED=1 FINE_PREAD=1` | 当前默认，page cache 全覆盖 |
| **B. Fadvise (半诚实)** | `FINE_BUFFERED=1 FINE_PREAD=1 FINE_FADVISE=1` + `drop_caches` | DEC-039 协议，查询间驱逐 |
| **C. O_DIRECT (完全诚实)** | `FINE_DIRECT=1 FINE_PREAD=1` | 绕过 page cache，每次 I/O 到磁盘 |

### 测试矩阵

| 数据集 | cgroup | 线程 | 参数 |
|--------|--------|------|------|
| SIFT1M | 512MB | 1T | K=10, EF=50, NQ=200, REFINE_EF=100, FLAT_VEC_MB=64, CACHE_MB=32 |
| SIFT1M | 512MB | 4T | 同上 |
| DEEP10M | 2GB | 4T | K=10, EF=50, NQ=200, REFINE_EF=300, FLAT_VEC_MB=64, CACHE_MB=32 |
| DEEP10M | 3GB | 4T | 同上 (有 DEC-056 数据对照) |

### 每组测试前

1. `echo 3 > /proc/sys/vm/drop_caches` (清除 page cache)
2. cgroup 限制内 warmup 1 轮 (仅 SIFT1M, DEEP10M warmup 跳过)
3. 3 轮取峰值

### 预期指标

| 指标 | A. Buffered | B. Fadvise | C. O_DIRECT |
|------|------------|-----------|-------------|
| SIFT1M QPS (1T) | ~2292 | ~842 (DEC-021 数据) | **? (待测)** |
| SIFT1M QPS (4T) | ~5247 | **?** | **?** |
| DEEP10M QPS (4T) | ~1506 | **?** | **?** |
| Recall | 95.70% | 95.70% | 95.70% |

> Recall 应不变（算法正确性与 I/O 路径无关），QPS 差距即 page cache 水分。

## 新增/修改条款

### 修改 DEC-030

DEC-030 当前将 FINE_DIRECT 定位为"诊断/测试模式"。本次实验后，根据结果
决定是否升级为"诚实基准测试的必要模式"。

### 新增 L1 条款

```markdown
## 诚实 I/O 基准协议 {#CON-HONEST-002}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.5 -->

性能基准测试 MUST 至少报告两组数据：
1. **Buffered**: FINE_BUFFERED=1 (含 page cache)
2. **Direct**: FINE_DIRECT=1 (O_DIRECT, 无 page cache)

报告 MUST 标注测量模式。仅报告 Buffered 模式数字 MUST 附带声明：
"此数字依赖 OS page cache，实际内存使用可能超过 cgroup 限制"。

> rationale: DEC-039 确立了诚实协议，但 drop_caches + fadvise 只解决查询间
> 复用。O_DIRECT 是唯一能完全消除 page cache 影响的方法。
```

### 新增决策记录

实验完成后生成 DEC-057: O_DIRECT 诚实基准测试结果

## 实施步骤

1. **修复 BUG-ALIGN**: pread 路径 buffer 改用 `posix_memalign`
2. **编译验证**: `make bench`
3. **SIFT1M 三组对照** (512MB cgroup, 1T + 4T)
4. **DEEP10M 三组对照** (2GB/3GB cgroup, 4T)
5. **生成 DEC-057**: 记录结果 + 水分分析
6. **更新 README**: 双模式数字 (buffered / direct)

## 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| O_DIRECT 对齐 bug 修复后仍有问题 | 低 | 实验阻塞 | io_uring 路径已验证可用，可作 fallback |
| DEEP10M O_DIRECT QPS 极低 (<100) | 中 | 叙事受冲击 | 这正是 100M 必要性的证据 |
| Recall 在 O_DIRECT 下下降 | 极低 | 算法问题 | 不应发生，I/O 路径不影响算法 |
