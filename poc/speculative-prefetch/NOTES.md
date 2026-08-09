# Notes: Speculative Prefetch POC

> 创建: 2026-08-09
> Trunk SHA: 3e98f3e
> Status: EXPLORING (R0 corrected, directions revised)

## 背景

DiskHNSW 的 I/O 路径：`bg_thread sched_yield → fadvise(WILLNEED) → kernel readahead → pread`

Trunk profiling (SHA=4697c0d, 256MB 1T EF=100):
- 内核 43.7% > 用户 38.5% > libc 8.4%
- bg_thread sched_yield 自旋 ~18.4%, PQ ADC 10.3%, 图搜索 6.4%
- 每 query: pread=50.8, fadvise=42.4, sched_yield=2,116

VelesDB prefetch 策略：
1. CPU cache prefetch (`_mm_prefetch` / ARM `PRFM`) — 在 candidate list 遍历时提前 N 步
2. Multi-level: L1/L2/L3 分层预取
3. `calculate_prefetch_distance(dimension)` 按维度动态计算

## R0: Baseline Profiling — CORRECTED (cgroup, 2026-08-09)

**初次测量错误**: 未使用 cgroup, page cache 充足, FineRerank 显得不重要
**修正后**: 在 256MB cgroup + drop_caches 下重新测量

### 修正数据 (3轮×1000q, 256MB cgroup, perf stat)

**整体性能**: agg=831 QPS / steady=1099 QPS / 1203 us/query

**CPU/Cache Profile (per query)**:
- Instructions: 15.7M, IPC=2.21
- **LLC miss rate: 51.3%** (8,270 次/query) ← disk I/O 体现
- L1-dcache miss: 0.5% (PQ ADC 在 cache 中)
- Cache miss rate: 47.1%
- **Page faults: 44.8/query** ← page cache miss → disk read
- Context switches: 15.1/query

**时间分解**:
- Graph search (含 block I/O): 1202 us (99.98%) ← **真正瓶颈**
- FineRerank: 0.29 us (0.02%) ← WILLNEED 已预读

### 结论

**DiskHNSW 确实是 disk I/O 密集型**。瓶颈在 graph search 内部的 block loading,
不在 FineRerank。

原 R1/R2/R3 针对的 FineRerank 不是瓶颈。需要重新定向:

| 新方向 | 目标 | 方法 |
|--------|------|------|
| R4 | block layout | BFS → 优化 page locality |
| R5 | graph_prefetcher 增强 | 2-hop / 推测性 block 预取 |
| R6 | PQ ADC cache | codebook 布局 (但 L1 miss 已低, 可能无收益) |

Evidence: `ndf/evidence/r0-baseline-profiling-20260809.md`
