# DEC-098: BFS-supervised k-means 负结果 — graph penalty 无法引导聚类 {#DEC-098}

> date: 2026-08-12
> affects: BEH-037, DEC-096
> Rejects: bfs-cluster

## Context

vecblock-cluster-reorder（DEC-096）已 promote pure k-means within-block sort。
bfs-cluster POC 假设：在 k-means assignment 中加入 BFS graph neighbor penalty，
可同时优化向量相似度与 graph 连接度，改善 I/O 局部性。

依赖：vecblock-cluster-reorder (promoted)；探索面：
`cluster-vecblock-layout`, `vecblock-layout`。

## 实验

256MB cgroup，sustained golden，k=1024，λ ∈ {1.0, 100}，对比 pure k-means baseline。

| λ | graph_aligned | Cluster sizes (min/max/avg) | QPS | vs pure |
|---|---------------|----------------------------|-----|---------|
| 1.0 | 0.4–0.5% | ≈ pure | ≈ pure | 无分离 |
| 100 | 0.4–0.5% | 309 / 3916 / 977 (pure: 265/3894/977) | 1,774 | −2.1% (1,812) |

Mechanism 正常（λ=100 改变 cluster size 分布），但 graph_aligned 无提升。

## 根因分析

1. k=1024 clusters，avg ~26 neighbors/node → 每 cluster 每节点仅 ≤2–3 neighbor
2. Graph penalty λ×N_c ≪ centroid distance gap (~100–1000)
3. HNSW graph neighbors 在向量空间中刻意 diverse → graph signal 太稀疏

## 结论

- **BFS-supervised k-means 不可行** — graph penalty 无法在 k=1024 规模引导 cluster 分离
- **不 promote 任何条款** — 无 topic-owned draft
- 负结果闭环：TOPIC=rejected，binder archive，Trunk 保持 BEH-037 pure k-means

> source: poc/bfs-cluster/NOTES.md ; poc/bfs-cluster/ndf/TOPIC.md ; run_r0.sh @ 2026-08-10
> Rejects: bfs-cluster
