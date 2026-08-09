# Notes: Speculative Prefetch POC

> 创建: 2026-08-09
> Trunk SHA: 3e98f3e
> Status: EXPLORING

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

## R0: Baseline Profiling — DONE (2026-08-09)

**结果: REJECTED (负结果)**

FineRerank 仅占 0.06% 查询时间（0.4 us/query），graph search 占 99.94%（714.6 us/query）。
所有 prefetch 路径已被前序 POC 优化，speculative prefetch 无收益空间。

| 方向 | 裁决 | 理由 |
|------|------|------|
| R1 CPU prefetch PQ ADC | ❌ REJECT | 占 0.004% |
| R2 Speculative WILLNEED | ❌ REJECT | 占 0.054% |
| R3 Batch prefetch pipeline | ❌ REJECT | 占 0.058% |

Evidence: `ndf/evidence/r0-baseline-profiling-20260809.md`
