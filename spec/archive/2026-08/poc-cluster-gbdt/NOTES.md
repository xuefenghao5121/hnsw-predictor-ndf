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

## 2026-08-13 amendment note

R0 结论保持不变，但它只覆盖旧 Trunk / k=1024 purity 特征。主题仍为 `exploring`；
在已优化 cluster layout 前提下的 entropy / per-cluster signal 仅登记为 R1 candidate。
现行 Trunk R0 未重测前，不宣称正结果，也不自动选择 reject/close。

## R1 结果: cluster entropy 无增量信号 (2026-08-14, Trunk a143392)

A1 candidate（cluster entropy 取代单一 purity）在现行 Trunk 上重测。groundtruth top-100
（官方 9999 queries, k=1024）:

| 特征 | mean | 解读 |
|------|-----:|------|
| normalized entropy | 0.9945 | 饱和（max=1.0），几乎无 per-query 方差 (std 0.0038) |
| purity | 0.0634 | top-100 横跨 ~94/1024 cluster，无聚集 |
| dominant_frac | 0.0237 | 主导 cluster 仅占 ~2.4% 候选 |

**结论**: 顶部候选在 cluster 空间近乎均匀分布（entropy 饱和），cluster 聚集信号本身
不存在。A1 不提供超出距离特征的增量信息，与 R0 的 purity 负结果一致 —— 该负结果
不是 k=1024 粒度伪影。

- A2 (k=4096/8192) 与 A3 (per-cluster predictor) 仍 `deferred`，门在 A1 显示增量趋势 —— 未显示；负结果关闭后不启动。
- 未启动 heavy PQ coarse simulation（entropy 分析已给出决定性负结果；Human 明令不启动）。
- 主题 `rejected`（2026-08-15，[[DEC-099]]）。未来若改 k 粒度或 graph 密度前提，MUST 开平级新 topic。

Evidence: `ndf/evidence/r1-entropy-analysis-20260814.md` + `.log`
