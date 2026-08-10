# Topic: cluster-gbdt

> ndf_topic: cluster-gbdt
> status: exploring
> created: 2026-08-10
> explore_surface: spec/20-behavior/learned-pruning
> depends_on_topics: vecblock-cluster-reorder (promoted)
> baseline_status: current
> baseline_trunk_sha: 1f684c7
> baseline_protocol: CON-SLA-020 sustained

## Hypothesis

Cluster sort (BEH-037) 使相似向量集中 → 粗排 top candidates 可能集中在少数 cluster。
加 cluster 特征到 GBDT → 预测"高 cluster 纯度 = 更少精细候选即可"→ 更激进剪枝 → 更快 fine rerank。

方法: node_id → cluster_id 查找表 + cluster 熵/纯度特征 → retrain GBDT。

## Directions

### R0: cluster feature GBDT
- 生成 cluster_id.bin (node_id → cluster)
- 加 cluster 纯度特征 (top-200 中 unique clusters / 200)
- Retrain GBDT with 12 features
- A/B: standard GBDT vs cluster-GBDT @1T 256MB

## Perf Baseline

见 ndf/PERF_BASELINE.md
