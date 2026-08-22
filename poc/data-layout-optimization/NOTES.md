# Notes: Data Layout Optimization POC

> 创建: 2026-08-09
> Trunk SHA: 3e98f3e
> Status: R0 DONE — REJECTED (天花板不足)

## R0: Cache Locality Analysis — DONE (2026-08-09)

### 核心数据

**BFS vs Random vs Original** (1M nodes, avg 21.2 neighbors):

| 指标 | BFS | Random | Original |
|------|-----|--------|----------|
| PQ CLs touched (mean) | 20.76 | 21.21 | 21.21 |
| PQ reuse (nbrs/CL) | 1.02 | 1.00 | 1.00 |
| CSR reuse (nbrs/CL) | 1.06 | 1.00 | 1.00 |

**BFS 仅比 random 好 2-6%。几乎无 cache line sharing。**

### 根因

1. PQ code = 32B = 半 cache line → 每 CL 仅 2 个节点
2. 理论最优 = 21.2/2 = 10.6 CLs，实际 BFS = 20.76 (1.9x 差距)
3. BFS 降低 ID spread (329K vs 901K) 但不足以实现 CL sharing
4. Coleman 论文 40% 提升基于 full vectors (512B)，我们 PQ (32B) 受限

### 改进天花板

- 乐观估计 PQ sharing 从 1.02→1.5 → 节省 ~519 LLC misses/query
- 有效延迟节省 ~39 us (4.1% QPS)
- 低于 5% 可靠 A/B 测量阈值

### 结论

**R0 REJECTED — 天花板 ~4% QPS，不值得做实验。**

Evidence: `ndf/evidence/r0-analysis-20260809.md`
