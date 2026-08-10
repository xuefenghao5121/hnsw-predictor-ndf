# page-packer — Notes
> status: exploring | created: 2026-08-10

## Method
Pipeline: cluster_reorder → page_packer
1. k-means cluster sort (within-block)
2. Per-cluster-segment greedy page packing (DEC-018 algorithm)

Each cluster segment in a block (~2.3 vectors on average) gets packed with
graph neighbors onto same 4KB page when possible.

## R0 结果: cluster sort + page packing (2026-08-10)

| | QPS | steady | recall |
|--|:---:|:---:|:---:|
| A: cluster only | 1,744 | 2,045 | 96.60% |
| B: cluster + pack | 1,769 | 2,065 | 96.60% |
| Δ | **+1.4%** | +1.0% | 0 |

### 分析

Page packing 边际收益 +1.4%（可能 run-to-run noise）。
shuffle_vecblocks 对 cluster-sorted blocks 只有 ~2.3 vectors/cluster/block
可供重排 → 优化空间有限。

### 结论

**Marginal positive** — 收益小于 cluster sort 本身的 +26.5%。
Page packing 不是方向 B 的主要收益来源。
