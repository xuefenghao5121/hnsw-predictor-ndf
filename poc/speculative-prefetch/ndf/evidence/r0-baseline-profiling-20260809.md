# R0 Evidence: Baseline Profiling — Speculative Prefetch POC

> 日期: 2026-08-09
> Trunk SHA: 3e98f3e
> 配置: SIFT1M 1T 256MB EF=100 (配置 A), cgroup v2 drop_caches
> 协议: PROFILE_TS=1, perf stat, 3 rounds × 1000 queries, seed=42

## 重要纠正

初次 R0 测量 **未使用 cgroup**，导致 page cache 充足，FineRerank 显得不是瓶颈。
在 256MB cgroup + drop_caches 下重新测量后，发现真正的 disk I/O 瓶颈在 graph search 内部。

## 修正数据 (256MB cgroup, 3 rounds × 1000q)

### 整体性能

```
CSV_AGG,3,3000,3.607761,831.5,97.71,2714,1099.2
```
- agg QPS: 831.5
- steady QPS: 1099.2
- per-query latency: 1203 us (agg)

### Perf stat (3000 queries total)

| 指标 | 总计 | Per-query |
|------|------|-----------|
| Instructions | 47.2B | 15.7M |
| Cycles | 21.3B | 7.1M |
| IPC | 2.21 | — |
| L1-dcache misses | 228.4M | 76,119 |
| **LLC loads** | 48.4M | 16,131 |
| **LLC misses** | 24.8M | **8,270** |
| **LLC miss rate** | — | **51.3%** |
| Cache references | 367.6M | 122,547 |
| Cache misses | 173.2M | 57,730 |
| Cache miss rate | — | 47.1% |
| Branch misses | 86.8M | 28,935 |
| Context switches | 45,449 | 15.1 |
| Page faults | 134,467 | **44.8** |

### PROFILE_TS timing

| n | pread (us) | rerank (us) |
|---|-----------|------------|
| 200 | 3441 | 77 |
| 1000 | 1363 | 34 |
| 2000 | 986 | 21 |
| 3000 | 853 | 17 |

Per-query (steady state, n=3000): pread=0.284 us, rerank=0.006 us

### 时间分解

| 组件 | 时间/query | 占比 |
|------|-----------|------|
| Graph search (含 block I/O) | 1202 us | **99.98%** |
| FineRerank pread | 0.284 us | 0.024% |
| FineRerank rerank | 0.006 us | 0.001% |

## 分析

### 为什么 FineRerank 不是瓶颈？

WILLNEED bg_thread 在 graph search 期间预读了 FineRerank 需要的页。
当 FineRerank 开始时，页面已在 page cache，pread 命中内存而非磁盘。

### 真正的 disk I/O 瓶颈在哪里？

**Graph search 内部的 block loading:**
1. `cache_->getBlockById()` cache miss → 同步磁盘读取 (64KB block)
2. `graph_prefetcher_->submitPrefetch()` 做了 1-hop 预取，减轻了但不能消除
3. LLC miss rate 51.3% 证实了大量内存/磁盘访问
4. Page faults 44.8/query 证实了 page cache miss → kernel 分配新页面 → disk I/O

### 对比：无 cgroup vs 256MB cgroup

| 配置 | QPS | FineRerank pread (us/q) |
|------|-----|------------------------|
| 无 cgroup (热缓存) | 1398 | 0.384 |
| 256MB cgroup | 831 | 0.284 |

FineRerank 两者都极小（< 1 us），因为 WILLNEED 在两种情况下都有效。

## 方向裁决

原方向 (R1/R2/R3) 针对的 FineRerank 不是瓶颈。POC 方向需要重新定义。

| 原方向 | 目标 | 占比 | 裁决 | 理由 |
|--------|------|------|------|------|
| R1 CPU prefetch PQ ADC | rerank compute | 0.001% | ❌ REJECT | 占比可忽略 |
| R2 Speculative WILLNEED | FineRerank pread | 0.024% | ❌ REJECT | 占比可忽略 |
| R3 Batch prefetch pipeline | FineRerank overlap | 0.025% | ❌ REJECT | 占比可忽略 |

### 新方向候选

| 新方向 | 目标 | 估算收益 |
|--------|------|---------|
| R4 block layout 优化 | 减少 page fault 次数 | 取决于 BFS locality 改进 |
| R5 graph_prefetcher 2-hop | 减少 block cache miss | 可能减少同步等待 |
| R6 PQ codebook cache | 减少 L2 miss | L1 miss 已 0.5%, 收益有限 |

## 来源

- perf log: `/tmp/r0_perf2.log`
- CSV output: `/tmp/r0_perf2_out.log`
- PROFILE_TS: `/tmp/r0_perf2.log`
- code: `src/core/disk_hnsw.cpp:searchLayer0()` (line 390+)
