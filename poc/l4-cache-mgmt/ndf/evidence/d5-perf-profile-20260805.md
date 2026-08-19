# Evidence: D5 - Post-A2+C2 perf Profile

> 日期: 2026-08-05
> 协议: perf record during CON-SLA-014 benchmark
> 配置: 512MB/256MB, 16T, WILLNEED_BG=1 VL_POOL_THREADS=14

## 512MB 16T (QPS=25,339)

排除 init (buildInMemoryAdjacency 11%):

| 排名 | 开销 | 函数 | 分类 |
|------|------|------|------|
| 1 | 5.42% | pqDistance | PQ 计算 |
| 2 | 2.46% | searchLayer0 | 图遍历 |
| 3 | 2.13% | std::thread::_M_run (BG thread yield) | 调度 |
| 4 | 1.65% | insertion_sort (pages_needed) | 排序 |
| 5 | 1.29% | _copy_to_iter (pread) | I/O |
| 6 | 1.04% | __sched_yield (BG thread) | 调度 |
| 7 | 0.87% | vector::reserve | 内存分配 |
| 8 | 0.85% | zap_present_ptes (page table) | 内核 |
| 9 | 0.84% | decodeCsrNeighbors | CSR 解码 |
| 10 | 0.78% | _raw_spin_lock | 内核锁 |

**无单一显著瓶颈** -- 最大搜索项 pqDistance 仅 5.42%。

## 256MB 16T (QPS=15,283)

排除 init:

| 排名 | 开销 | 函数 | 分类 |
|------|------|------|------|
| 1 | 6.63% | intel_idle | CPU 空闲 (I/O 等待) |
| 2 | 5.22% | pqDistance | PQ 计算 |
| 3 | 3.43% | malloc_consolidate | 内存分配 |
| 4 | 2.59% | searchLayer0 | 图遍历 |
| 5 | 1.76% | BG thread _M_run | 调度 |
| 6 | 1.24% | insertion_sort | 排序 |
| 7 | 1.03% | _copy_to_iter (pread) | I/O |
| 8 | 1.02% | decodeCsrNeighbors | CSR 解码 |
| 9 | 0.85% | memset | 内存清零 |
| 10 | 0.72% | clflush_cache_range | 内核 cache flush |

**intel_idle 6.63%**: CPU 在等待 I/O，说明 256MB 下仍有 I/O 瓶颈。

## 对比旧 profile (pre-A2+C2, 12T)

| 项目 | 旧 12T | 新 16T 512MB | 新 16T 256MB |
|------|--------|-------------|-------------|
| WILLNEED 锁竞争 | 6.27% | **0%** (BG 消除) | **0%** |
| VisitedList memset | 10.29% | 0.85% (pool) | 0.85% (pool) |
| pqDistance | 未测 | 5.42% | 5.22% |
| intel_idle (I/O wait) | 未测 | 4.39% | **6.63%** |
| BG thread yield | N/A | 1.04% | 0.68% |

## 瓶颈迁移分析

| 瓶颈 | 旧状态 | 新状态 | 说明 |
|------|--------|--------|------|
| WILLNEED 内核锁 | 6.27% | **消除** | A2 BG 线程解决 |
| VisitedList memset | 10.29% | **0.85%** | C2 池化解决 |
| PQ 计算 | ? | **5.2%** | 新 #1 热点 (但难优化) |
| I/O 等待 | ? | **4.4-6.6%** | 256MB 下仍显著 |
| 内存分配 | ? | **3.4%** (256MB) | malloc_consolidate |

## 可优化方向

1. **pqDistance (5.2%)**: SIMD AVX2 LUT 已优化，进一步提升需要 AVX-512 或量化
2. **intel_idle (6.6% @256MB)**: I/O 等待，D2 BG merge 已部分解决
3. **malloc_consolidate (3.4% @256MB)**: 频繁分配/释放 (pread buffer posix_memalign)
   - 可改为预分配 buffer pool
4. **BG thread yield (1.0%)**: sched_yield 开销，可改为 relaxed spinlock 或 io_uring
5. **insertion_sort (1.2-1.7%)**: pages_needed 排序，可去掉或用 radix sort

## 结论

A2+C2 后无单一显著瓶颈 (>10%)。性能已接近该架构的 Pareto 前沿。
剩余优化空间分散在 PQ 计算 (5%)、I/O 等待 (5-7%)、内存分配 (3%) 等多个小项。
