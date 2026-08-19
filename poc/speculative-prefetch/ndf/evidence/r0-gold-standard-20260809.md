# R0 Evidence: Gold Standard Baseline Profiling (Final)

> 日期: 2026-08-09
> Trunk SHA: 3e98f3e
> 配置: 金标配置 A (SIFT1M M=16 EF=100, 256MB 1T cgroup)
> 协议: 15 rounds × 1000 queries, seed=42, cgroup v2 drop_caches
> 工具: PROFILE_TS=1 + perf stat (cache events + page fault breakdown)

## 性能

| 指标 | 值 |
|------|-----|
| agg QPS | 1,052 |
| steady QPS | 1,149 |
| per-query latency | 950 us |
| recall@10 | 97.76% |

## 瓶颈定位（三维度）

### 1. Disk I/O — 仅 0.50 major faults/query (3%)

| 指标 | 值 |
|------|-----|
| Major faults (disk) | 7,428 total → **0.50/query** |
| Minor faults (memory) | 126,881 total → 8.46/query |
| 估算 disk I/O 时间 | ~25 us/query (3% of latency) |

**disk I/O 已被 WILLNEED bg_thread + graph_prefetcher_ 完全覆盖。**

### 2. CPU L1 cache — 良好 (2.2% miss rate)

| 指标 | 值 |
|------|-----|
| L1-dcache loads | 2.8M/query |
| L1-dcache misses | 61,372 (2.2%) |

**PQ ADC 计算在 L1/L2 cache 中，无优化空间。**

### 3. LLC (Last-Level-Cache) — 真正的瓶颈 (58.1% miss rate)

| 指标 | 值 |
|------|-----|
| LLC loads | 8,754/query |
| LLC misses | **5,087/query (58.1%)** |
| 估算 DRAM latency | ~1,017 us/query (overlap with compute) |
| IPC | 2.37 |

**LLC miss 是性能杀手**。原因：内存数据结构总量 ~240MB，远超 L3 cache (~30MB)。
随机访问 CSR adjacency (47MB) + PQ codes (30MB) + block cache (64MB) 导致频繁 cache miss。

### graph_prefetcher_ 在 PQ 模式下不工作

```
[Prefetch Accuracy] useful=0 wasted=0 total_prefetched_settled=0 accuracy=0%
```

PQ 模式跳过 graph_prefetcher_（代码 `src/core/disk_hnsw.cpp:497`）：
> "PQ 模式跳过: 不走向量 I/O, 预取只会堵精排队列"

## 时间分解

```
┌─ Query latency (950 us) ──────────────────────────────────┐
│                                                           │
│  ├─ LLC miss → DRAM latency: ~700 us (74%)              │
│  │   (部分被 out-of-order execution 隐藏, IPC=2.37)      │
│  │   - CSR adjacency access (47MB, random pattern)      │
│  │   - PQ codes access (30MB, random pattern)           │
│  │   - Block cache access (64MB, LRU eviction)          │
│  │                                                        │
│  ├─ Disk I/O: ~25 us (3%)                               │
│  │   (major fault 0.50/query, covered by WILLNEED)       │
│  │                                                        │
│  └─ CPU compute: ~225 us (24%)                          │
│      (PQ ADC SIMD, visited list, heap operations)        │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

## VelesDB 策略适用性

| VelesDB 策略 | 我们的状况 | 适用性 |
|-------------|-----------|--------|
| CPU cache prefetch (`_mm_prefetch`) | L1 miss 2.2% | ❌ 无收益 |
| I/O prefetch (fadvise) | Major fault 0.50/q | ❌ 已覆盖 |
| Contiguous layout + BFS reorder | 已有 BFS, 但 LLC miss 58% | ⚠️ 可改进布局 |
| `prefetch_distance = f(dimension)` | graph_prefetcher_ 在 PQ 模式跳过 | ❌ 不适用 |

## 结论

**VelesDB 的 speculative prefetch 不适用于我们的 PQ-based disk ANN 架构。**

1. Disk I/O 已被现有 prefetch 机制覆盖 (major fault 仅 0.50/query)
2. CPU L1 cache 已优化 (miss rate 2.2%)
3. 真正瓶颈是 LLC miss (58.1%) → DRAM latency on in-memory data structures
4. graph_prefetcher_ 在 PQ 模式下完全不工作 (useful=0)

## 来源

- perf log (cache events): `/tmp/r0_gold_256_1t.perf`
- perf log (page faults): `/tmp/r0_majfaults.log`
- CSV output: `/tmp/r0_gold_256_1t.out`
- code: `src/core/disk_hnsw.cpp:searchLayer0()` (line 390)
