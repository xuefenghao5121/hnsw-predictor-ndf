# Topic: Speculative Prefetch (VelesDB-inspired)

> status: rejected
> track: poc
> created: 2026-08-09
> closed: 2026-08-09
> baseline_trunk_sha: 3e98f3e
> baseline_status: current
> close_reason: VelesDB prefetch inapplicable — bottleneck is LLC miss (58.1%) not disk I/O (3%) or L1 miss (2.2%)

## 研究结果

R0 gold standard profiling 证实：
- Disk I/O: major fault 仅 0.50/query (3%) — WILLNEED 已覆盖
- CPU L1 miss: 2.2% — PQ ADC 在 cache
- LLC miss: 58.1% — 真正瓶颈 (DRAM latency on ~240MB data > L3 ~30MB)
- graph_prefetcher_: PQ 模式下完全跳过 (useful=0)

VelesDB 的 prefetch 策略 (CPU cache prefetch + I/O prefetch) 均不适用。

## 关联条款

- BEH-024 (WILLNEED), BEH-027 (WILLNEED_BG), DEC-070, DEC-074
- CON-GOLDEN-001 (golden config)
