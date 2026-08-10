# Topic: vecblock-cluster-reorder

> ndf_topic: vecblock-cluster-reorder
> status: promoted
> created: 2026-08-10
> explore_surface: spec/20-behavior/vecblock-layout
> depends_on_topics: none
> related_topics: ssd-parallelism-io (promoted)
> baseline_status: current
> baseline_trunk_sha: dc5696904e2fb0323f5b70286ce2b8029df64230
> baseline_protocol: CON-SLA-020 sustained, CON-SLA-014 strict cgroup, CON-SLA-019 禁预热
> reference: VLDB 2025 §5 "Spatial-Awareness Insertion Reorder" + §7 "Locality-Preserving Co-location"

## Hypothesis

向量按聚类重排 vecblock 布局 → 共访向量集中在更少的连续页上 →
per-query I/O 页数减少 → QPS 提升。

当前 Profile (R2 from ssd-parallelism-io): 44.6 pages/query, 17.6 cached.
目标: <30 pages/query, 提升 coarse + fine 双阶段性能。

## Directions

### R0: k-means 聚类 + 离线重排
- 对 SIFT1M 训练集做 k-means (k=256/512/1024 簇)
- 按簇 ID 排序向量，重新写入 vecblock 文件
- 保持 BFS 顺序在簇内
- A/B: 原版 vs 重排版, sustained golden

### R1: 增量重排 (online-friendly)
- 类似论文 §5 的空间感知插入: 动态调整插入位置
- 评估对增量插入的影响

### R2: 混合方案
- CQE peeking (已 promote) + cluster reorder 复合收益

## Perf Baseline

见 ndf/PERF_BASELINE.md

## Notes

见 ../NOTES.md
