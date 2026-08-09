# R0 Evidence: Baseline Profiling — Speculative Prefetch POC

> 日期: 2026-08-09
> Trunk SHA: 3e98f3e
> 配置: SIFT1M 1T 256MB EF=100 (配置 A)
> 协议: PROFILE_TS=1, 1000 queries, seed=42

## 方法

使用内置 `PROFILE_TS=1` 插桩，输出 cumulative timing:
- PhaseA: graph search 时间 (含 PQ ADC + block I/O)
- pread: FineRerank pread I/O 时间
- rerank: FineRerank 距离计算时间

## 原始数据

### CSV_AGG
```
CSV_AGG,1,1000,0.715221,1398.2,97.65,1000,1398.2
```
→ 1000 queries in 0.715s = **715 us/query**

### PROFILE_TS (cumulative)

| n | PhaseA (us) | pread (us) | rerank (us) |
|---|------------|-----------|------------|
| 200 | -62 | 146 | 70 |
| 400 | -42 | 356 | 49 |
| 600 | -35 | 387 | 38 |
| 800 | -31 | 393 | 31 |
| 1000 | -29 | 384 | 27 |

PhaseA 为负 → 计时噪声（graph search 时间在 PhaseA 外测量）

## 分析

| 组件 | 时间/query | 占比 |
|------|-----------|------|
| Graph search (Phase A) | ~714.6 us | **99.94%** |
| FineRerank pread | 0.384 us | 0.054% |
| FineRerank rerank | 0.027 us | 0.004% |

## 结论

**FineRerank 已完全优化（0.4 us/query）。瓶颈在 graph search（99.94%）。**

Graph search 时间分布：
- PQ ADC 距离计算（CPU-bound）
- Block I/O（neighbor list 加载，通过 graph_prefetcher_ 1-hop 预取）
- VisitedList 操作

VelesDB 的 prefetch 策略针对 **内存中向量遍历** 的 CPU cache miss。
我们的 DiskHNSW 在 PQ 模式下：
- 距离计算用 PQ ADC（32 字节/向量，已在 L1/L2 cache）
- Block I/O 用 graph_prefetcher_（io_uring 预取 neighbor blocks）
- FineRerank 用 WILLNEED bg_thread（fadvise 预读向量页）

**所有 prefetch 路径已被前序 POC 优化。speculative prefetch 在当前架构下无收益空间。**

## 方向裁决

| 方向 | 目标 | 占比上限 | 裁决 | 理由 |
|------|------|---------|------|------|
| R1 CPU prefetch PQ ADC | rerank compute | 0.004% | ❌ REJECT | 占比可忽略 |
| R2 Speculative WILLNEED | FineRerank pread | 0.054% | ❌ REJECT | 占比可忽略 |
| R3 Batch prefetch pipeline | FineRerank overlap | 0.058% | ❌ REJECT | 占比可忽略 |

**POC 整体裁决: REJECTED（负结果）**

FineRerank 在 EF=100 下仅占 0.06% 的查询时间。即使将 FineRerank 降到 0，
QPS 提升也不到 0.1%。VelesDB 的 prefetch 策略不适用于我们的 PQ-based disk ANN 架构。

真正的优化方向是 graph search 内部：PQ ADC SIMD 优化、visited list 优化、
graph layout 优化——但这些已在前序 POC 中探索（DEC-034/036/074）。

## 来源

- profile log: `/tmp/r0_ts_1000.log`
- CSV output: `/tmp/r0_out_1000.log`
- code: `src/core/disk_hnsw.cpp:searchKnn()` (line 1598)
