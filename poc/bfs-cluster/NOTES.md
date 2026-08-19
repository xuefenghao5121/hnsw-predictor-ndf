# bfs-cluster — Notes

> status: rejected | created: 2026-08-10 | closed: 2026-08-12
> Rejects: bfs-cluster | DEC-098

## Background

Pure k-means cluster sort (BEH-037) 只考虑向量距离，不感知 HNSW graph 结构。
结果：BFS graph neighbors 被分散到不同 cluster → 同 cluster 块内包含了非 neighbor 向量。

## Method

BFS-Supervised k-means: 在 assignment 步中加入 graph penalty 项：
  assignment(i) = argmin_c [ ||v_i - μ_c||² - λ × N_c(i) ]
其中 N_c(i) = 在 cluster c 中 v_i 的 neighbor 数量。

Higher λ = 更强的 graph 保持力。

## R0 结果: BFS-supervised k-means (2026-08-10)

### λ=1.0
- graph_aligned: 0.4-0.5% (negligible)
- Cluster assignment = pure k-means

### λ=100
- graph_aligned: 0.4-0.5% (same — no effect!)
- Cluster sizes: min=309 max=3916 avg=977 (pure: 265/3894/977)
- QPS: 1,774 vs pure k=1024 1,812 (−2.1%)

### 根因

With k=1024 clusters and avg 26 neighbors/node:
- Each cluster has ≤2-3 neighbors per node on average
- Graph penalty λ×N_c is overwhelmed by centroid distance (gap ~100-1000)
- HNSW graph neighbors are intentionally DIVERSE (by construction)
- Graph signal too sparse to guide cluster assignment at k=1024

### 结论

**BFS-supervised k-means = 负结果 ❌**
方向 E 不可行：HNSW graph 邻居分散在向量空间中 → graph penalty 无法有效引导聚类。
