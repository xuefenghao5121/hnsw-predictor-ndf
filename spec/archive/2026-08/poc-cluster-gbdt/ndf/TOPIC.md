# Topic: cluster-gbdt

> ndf_topic: cluster-gbdt
> status: rejected
> created: 2026-08-10
> closed: 2026-08-15
> baseline_status: n/a
> baseline_trunk_sha: a143392
> baseline_protocol: CON-SLA-020 sustained
> perf_baseline: ndf/PERF_BASELINE.md
> next_gate: n/a
> selected_decision: reject
> rejects_dec: DEC-099
> archive: spec/archive/2026-08/poc-cluster-gbdt/

<!-- ndf:gate-slice begin=topic_contract -->
> explore_surface: spec/20-behavior/learned-pruning
> depends_on_topics: vecblock-cluster-reorder (promoted)
> active_hypothesis: R1 — 在已优化的 cluster layout / 现行 Trunk 前提下，cluster entropy 或 per-cluster signal 可能提供旧 purity 特征没有的增量信息
> open_decision: 先重测现行 Trunk R0，再决定 amend/continue_exploring/reject；尚未选择关闭

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

### R1 candidate: updated prerequisite re-evaluation

- 保留 R0「k=1024 purity 无显著收益」为历史负结果，不重写。
- 先对现行 Trunk 重测 R0，恢复 `baseline_status=current`。
- 若 R0 证明前提已变化，再比较 cluster entropy / 更细粒度 k / per-cluster signal；
  当前仅为候选假设，尚未获实现或关闭决策。
<!-- ndf:gate-slice end=topic_contract -->

## Verdict

**A1 cluster entropy = 负结果。** R1（Trunk a143392，k=1024）entropy 饱和 0.9945，
purity 0.063，top-100 横跨 ~94/1024 clusters，无聚集。A2/A3 门在 A1 增量趋势，未满足；
PQ simulation 不启动。详见 [[DEC-099]]。`Rejects: cluster-gbdt`。

## Perf Baseline

见 ndf/PERF_BASELINE.md
