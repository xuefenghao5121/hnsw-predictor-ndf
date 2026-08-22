# Evidence: Bottleneck Profiling - SIFT1M 4T vs 12T

> 日期: 2026-08-05
> 协议: perf record -g --call-graph dwarf, 512MB cgroup, CON-SLA-014
> 数据集: SIFT1M, 200 queries, k=10, ef=100, L4_WILLNEED=1

## 实验设计

对比 4T（高效，9657 QPS）和 12T（停滞，17610 QPS）的 perf profile，
找出 scaling 从 3.52x（4T）降至 6.42x（12T，远低于 12x 线性）的瓶颈。

## 核心发现

### 瓶颈 #1: posix_fadvise(WILLNEED) 内核锁竞争 (6.27%)

**12T 新增的 kernel 热点全部来自 `posix_fadvise(WILLNEED)` 调用链**：

| 函数 | 4T | 12T | 调用栈 |
|------|-----|-----|--------|
| osq_lock | 0% | 2.78% | -> rwsem_down_write_slowpath -> do_mprotect_pkey -> fadvise |
| queued_spin_lock_slowpath | 0% | 2.43% | -> __filemap_add_folio -> page_cache_ra_unbounded -> fadvise |
| down_read | 0% | 1.06% | -> force_page_cache_ra -> generic_fadvise -> fadvise |

**根因**: `L4_WILLNEED=1` 在每次 `searchKnn` 中调用 `posix_fadvise(WILLNEED)` 触发 readahead。
多线程并发调用时，内核 page cache 的 spinlock（`__filemap_add_folio`）和 rwsem（`do_mprotect_pkey`）产生严重竞争。

**讽刺**: WILLNEED 在 1T/256MB 下是 17.7x 加速，但在 12T+ 下成为最大瓶颈。

### 瓶颈 #2: VisitedList memset 翻倍 (5.38% -> 10.29%)

| 函数 | 4T | 12T | 变化 |
|------|-----|-----|------|
| __memset_avx2_unaligned_erms | 5.38% | 10.29% | +91% |

**根因**: 每个 `searchKnn` 创建一个 `VisitedList`（1M 节点 * 1B = 1MB），用 memset 清零。
更多线程 = 更多 VisitedList = 更多 memset。但占比翻倍说明 cache line bouncing
（多核写同一个 allocator 返回的内存区域）。

### 非瓶颈（排除项）

| 候选 | 4T | 12T | 结论 |
|------|-----|-----|------|
| pqDistance | 37.90% | 20.73% | 占比下降（不是瓶颈） |
| searchLayer0 | 20.66% | 9.62% | 占比下降 |
| pthread_mutex_unlock | 1.51% | 0% | BlockCache LRU 锁不是瓶颈 |
| malloc/free | ~2% | ~3% | 分配器压力轻微增加 |

## 优化方向（未来 POC 或 promote）

### 方向 A: WILLNEED 线程化 (高收益)
- **方案**: 单独后台线程调用 `posix_fadvise`，搜索线程不直接调用
- **预期**: 消除 6.27% kernel 锁竞争，12T QPS 预计 +10-15%
- **复杂度**: 中（需改 disk_hnsw.cpp 的 WILLNEED 调用路径）

### 方向 B: WILLNEED 自适应 (低复杂度)
- **方案**: `NUM_THREADS >= 8` 时自动禁用 WILLNEED
- **预期**: 消除竞争，但损失 WILLNEED 的 1T 加速
- **复杂度**: 低（仅环境变量检查）

### 方向 C: VisitedList 池化 (中等收益)
- **方案**: 线程局部 VisitedList 池，复用而非每次创建
- **预期**: 减半 memset 开销（10.29% -> ~5%）
- **复杂度**: 中（需改 searchKnn 的 VisitedList 管理）

## 结论

12T+ scaling 停滞的主要原因是 **L4_WILLNEED 的内核锁竞争**（6.27%），
其次是 **VisitedList memset 的 cache line bouncing**（10.29%）。
BlockCache LRU 锁和分配器不是瓶颈。
