# DEC-099: cluster-gbdt 负结果 — cluster entropy 饱和、无聚集 {#DEC-099}

> date: 2026-08-15
> affects: BEH-034, BEH-037
> Rejects: cluster-gbdt

## Context

vecblock-cluster-reorder（DEC-096 / [[BEH-037]]）已 promote pure k-means within-block
sort。cluster-gbdt 假设：cluster layout 使粗排 top candidates 集中在少数 cluster，
从而 cluster entropy / purity 能为 [[BEH-034]] GBDT 提供旧距离特征没有的增量信号。

依赖：vecblock-cluster-reorder (promoted)；探索面：`spec/20-behavior/learned-pruning`。

Human 判定（2026-08-14）：A1 已证伪（entropy 饱和、无聚集）。A2/A3 门在 A1 增量趋势，
未满足。走负结果关闭，不要再开 A2/A3 或 PQ simulation。

## 实验

R0（2026-08-10，历史）：12-feature GBDT + cluster purity；LEARNED_EF Δ 在噪声量级
（+1.0% / −0.7%）。purity 非增量信号。

R1（2026-08-14，Trunk `a143392`，k=1024 assignments，groundtruth top-100，
9999 queries）：

| 指标 | 值 | 判定 |
|------|-----|------|
| cluster entropy | 0.9945 | **饱和** — 分布近乎均匀 |
| purity | 0.063 | 无纯度聚集 |
| dominant_frac | 0.024 | 最大单 cluster 占比 2.4%，无主导 cluster |
| top-100 cluster span | ~94 / 1024 | top candidates 分散，**无聚集** |

## 根因

HNSW top-100 候选在 cluster layout（[[BEH-037]]，k=1024）上近乎均匀分布。
cluster entropy / purity / dominant_frac 均无法提供旧 purity 特征之外的增量信号。
A1（cluster entropy 取代单一 purity）被 R1 数据直接证伪。

A2（k=4096/8192）前置条件为「A1 有增量趋势」；A3（per-cluster predictor）前置条件为
「A1/A2 显示跨 cluster 异质性」。A1 证伪 → 两门均未满足 → A2/A3 保持 deferred，不启动。
PQ coarse simulation 同理由 Human 明令不启动。

## 结论

- **cluster entropy / purity 作为 GBDT 增量特征不可行** — 顶部候选在 cluster 空间无聚集
- **不 promote 任何条款** — 无 topic-owned draft；[[BEH-034]] / [[BEH-037]] 维持现状
- **不启动 A2/A3 或 PQ simulation**
- 负结果闭环：TOPIC=`rejected`，binder archive，Trunk 无需 revert（代码从未合入 `src/`）

未来若改变 k 粒度或 graph 密度前提，MUST 开平级新 topic（[[BEH-025]] 关闭后重启），
不得在本 topic 内重启 A2/A3。

> source: poc/cluster-gbdt/ndf/TOPIC.md ; poc/cluster-gbdt/NOTES.md ; poc/cluster-gbdt/ndf/evidence/r1-entropy-analysis-20260814.md ; poc/cluster-gbdt/ndf/DELTA.md ; poc/cluster-gbdt/ndf/COMMITS.md ; spec/open/proposal-reject-cluster-gbdt.md
> track: reject ; Topic: cluster-gbdt
> Rejects: cluster-gbdt
