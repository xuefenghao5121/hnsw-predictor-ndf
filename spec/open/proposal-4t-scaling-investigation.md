# Proposal: 4T Scaling 排查 - Post thread_local Fix

> track: poc
> 关联: [[DEC-063]]、[[BEH-021]]、[[CON-SLA-013]]、[[CON-POC-001]]
> 日期: 2026-08-02
> Status: Pending

## 1. 问题陈述

DEC-063 记录的 4T 数据（R1 4T=249.4, 0.89x of 1T=279.3）是 thread_local 修复**之前**的。
commit 7742330 修复了 `pipe_piped_pages_` / `pipe_page_bufidx_` 的线程竞争，
commit ed82b29 增加了内存优化（VisitedList uint8 + adjacency0 streaming free + malloc_trim）。
**Post-fix 4T 数据缺失**，无法判断：

- thread_local 修复是否解决了 4T 退化？
- 如果仍然差，瓶颈在哪里？

## 2. 排查计划

### Phase 1: Post-fix 4T Benchmark

**环境**: DEEP10M (10M/96D), 5GB cgroup, 10000 queries, k=10, ef=300, REFINE_EF=300
**Binary**: build/benchmark_pipe (含 thread_local fix + 内存优化)

| 轮次 | 配置 | 环境变量 |
|------|------|----------|
| R0 1T | baseline | FINE_BUFFERED=1 FINE_PREAD=1 EVICT_PAGE_CACHE=1 |
| R0 4T | baseline | + NUM_THREADS=4 |
| R1 1T | + pipe_ring_ | + PIPE_FINE=1 |
| R1 4T | + pipe_ring_ | + PIPE_FINE=1 NUM_THREADS=4 |

**目标**: R1 4T scaling ≥ 2.5x（vs R1 1T），R1 4T QPS ≥ 500

### Phase 2: 瓶颈定位（如果 scaling < 2.5x）

候选瓶颈（按优先级）：

1. **BlockCache mutex 竞争**
   - `getCachedBlockById()` 有 lock-free fast path（flat_block_ptrs_），但 miss 走 mutex
   - `peekCachedBlockById()` 每次都获取 mutex
   - searchLayer0 每个 candidate 至少 1 次 cache 查询
   - 4T = 4x mutex 竞争

2. **pread 系统调用竞争**
   - Phase B Fine Rerank 每个候选 1 次 pread
   - 4 线程同时 pread 同一 fd -> 内核 inode/page cache 锁
   - 但 pread 本身是线程安全的，瓶颈可能在 VFS 层

3. **内存分配器竞争**
   - Phase B 每个查询分配 `std::unordered_map<uint32_t, std::unique_ptr<char[]>>`
   - `std::set<uint32_t> pages_needed` 分配
   - glibc malloc 在多线程下有 arena 锁

4. **GraphPrefetcher mutex 竞争**
   - `submitPrefetch()` 和 `waitForBlocks()` 都有 mutex
   - searchLayer0 中频繁调用

5. **pipe_ring_ io_uring fd 竞争**
   - pipe_ring_ 本身是 thread_local，但 io_uring 提交可能内核层竞争

### Phase 3: 修复方案（基于 Phase 2 数据）

可能的修复方向（不改 src/，仅 poc/）：

- BlockCache: `std::mutex` -> `std::shared_mutex`（读多写少）
- 或: per-thread BlockCache 分片
- pread: 批量合并读取（但 DEC-061 Read Coalescing 已否决，需谨慎）
- 内存分配: 换 tcmalloc/jemalloc 或预分配池

## 3. 不做的事

- 不改 src/ 生产代码
- 不改 stable SLA 条款
- 不引用 pre-fix 4T 数据作为决策依据
