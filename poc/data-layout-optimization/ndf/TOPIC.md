# Topic: Data Layout Optimization for LLC Miss Reduction

> status: rejected
> track: poc
> created: 2026-08-09
> closed: 2026-08-09
> baseline_trunk_sha: 3e98f3e
> baseline_status: current
> close_reason: Layout optimization ceiling ~4% QPS, below reliable A/B threshold. BFS already provides 2-6% of available improvement. PQ code (32B) fundamentally limits CL sharing.

## 研究结果

R0 静态分析（全 1M 节点图）证实：

| 指标 | BFS | Random |
|------|-----|--------|
| PQ reuse (nbrs/CL) | 1.02 | 1.00 |
| CSR reuse (nbrs/CL) | 1.06 | 1.00 |
| 改进天花板 | ~4% QPS | — |

BFS reorder 几乎无效（2-6%），原因是 PQ code 仅 32B → 每 cache line 仅 2 节点。
Coleman 论文的 40% 提升基于 full vectors (512B)，不适用于 PQ-based 架构。

## 关联条款

- CON-GOLDEN-001 (golden config)
- META-006 (golden rerun rule)
