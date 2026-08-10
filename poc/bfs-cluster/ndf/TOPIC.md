# Topic: bfs-cluster

> ndf_topic: bfs-cluster
> status: exploring
> created: 2026-08-10
> explore_surface: spec/20-behavior/vecblock-layout, spec/20-behavior/cluster-vecblock-layout
> depends_on_topics: vecblock-cluster-reorder (promoted)
> baseline_status: current
> baseline_trunk_sha: 4a70704
> baseline_protocol: CON-SLA-020 sustained, CON-SLA-014 strict cgroup, CON-SLA-019 禁预热
> reference: BEH-037 (cluster vecblock layout), DEC-018 (page shuffle)

## Hypothesis

Pure k-means (BEH-037) 不感知 graph 结构 → BFS neighbors 可能分散到不同 cluster。
BFS-supervised k-means: 修改赋值目标函数 → 惩罚 neighbor 的 cluster 分离 → 
同时优化向量相似度 + graph 连接度 → 更好的 I/O 局部性。

## Directions

### R0: BFS-supervised k-means + within-block cluster sort
- 加载 graph adjacency (CSR)
- 修改 k-means assignment: distance = raw_dist - λ × neighbors_in_cluster
- 扫描 λ ∈ {0.1, 0.5, 1, 2, 5}
- A/B: pure k=1024 vs BFS-supervised k=1024, sustained golden

### R1: λ 调参 + 多线程 scaling
- 最优 λ 的 4T/16T 验证
- 可能的 Compound: CQE peeking + BFS-cluster

## Perf Baseline

见 ndf/PERF_BASELINE.md
