# cluster-gbdt — Notes
> status: rejected | created: 2026-08-10 | closed: 2026-08-15
> Rejects: cluster-gbdt | DEC-099 | proposal-reject-cluster-gbdt

## Method

1. Generate cluster_id[node_id] lookup from k-means assignments
2. During coarse search: lookup cluster for each top-K candidate
3. Compute cluster purity feature: unique_clusters / K
4. Add to GBDT features: [11 existing + 1 cluster_purity]
5. Retrain GBDT, run A/B

## R0 结果: GBDT + cluster (2026-08-10)

| Config | Default QPS | LEARNED_EF QPS | Δ |
|--------|:---:|:---:|:---:|
| BFS baseline | 1,442 | 1,456 | +1.0% |
| Cluster k=1024 | 1,812 | 1,800 | −0.7% |

### 分析

LEARNED_EF（现有 GBDT, 11 distance features）对 BFS 和 cluster 数据均无显著收益。
距离特征已编码大部分候选质量信息 → cluster purity 非增量信号。
GBDT 推理 + 剪枝开销 ≈ 回报。

### 结论

**方向 F = 无显著收益 ❌**
Cluster purity 不提供超出距离特征的增量信息。
GBDT 架构本身已足够（距离 → 候选质量），无需 cluster 特征。
