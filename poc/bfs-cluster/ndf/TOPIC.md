# Topic: bfs-cluster

> ndf_topic: bfs-cluster
> status: rejected (2026-08-12, DEC-098: BFS-supervised k-means graph penalty 无效)
> created: 2026-08-10
> closed: 2026-08-12
> explore_surface: spec/20-behavior/vecblock-layout, spec/20-behavior/cluster-vecblock-layout
> depends_on_topics: vecblock-cluster-reorder (promoted)
> baseline_status: current
> baseline_trunk_sha: 4a70704
> baseline_protocol: CON-SLA-020 sustained, CON-SLA-014 strict cgroup, CON-SLA-019 禁预热
> reference: BEH-037 (cluster vecblock layout), DEC-018 (page shuffle)
> rejects_dec: DEC-098
> archive: spec/archive/2026-08/poc-bfs-cluster/

## Hypothesis

Pure k-means (BEH-037) 不感知 graph 结构 → BFS neighbors 可能分散到不同 cluster。
BFS-supervised k-means: 修改赋值目标函数 → 惩罚 neighbor 的 cluster 分离 → 
同时优化向量相似度 + graph 连接度 → 更好的 I/O 局部性。

## R0 结果 (2026-08-10)

| λ | graph_aligned | QPS | vs pure k=1024 | 判定 |
|---|---------------|-----|----------------|------|
| 1.0 | 0.4–0.5% | ≈ baseline | — | 无分离 |
| 100 | 0.4–0.5% | 1,774 | −2.1% (1,812) | 无收益 |

## Verdict

**BFS-supervised k-means = 负结果。** Graph penalty 在 k=1024 下被 centroid 距离淹没；
HNSW neighbor 多样性使 graph signal 过于稀疏。详见 [[DEC-098]]。

## Directions (未执行)

### R1: λ 调参 + 多线程 scaling — 取消（R0 证伪）

## Perf Baseline

见 ndf/PERF_BASELINE.md
