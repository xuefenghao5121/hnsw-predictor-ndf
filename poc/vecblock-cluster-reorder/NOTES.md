# vecblock-cluster-reorder — Notes

> status: exploring
> created: 2026-08-10
> reference: VLDB 2025 "Turbocharging Vector Databases using Modern SSDs"
>   §5 Spatial-Awareness Insertion Reorder
>   §7 Locality-Preserving Co-location

## Background

当前 vecblock 布局: BFS 遍历 HNSW graph → 按遍历顺序写入 vecblock 页。
BFS 已提供一定的局部性（graph neighbor → nearby pages），但 graph 有全局跳边。

Profile (1T, 256MB, Config C): 44.6 pages/query fines rerank + 17.6 cache hits.
即使 CQE peeking 消除 I/O 等待，仍然有 44.6 次 I/O 请求 per query。

## Plan

聚类重排: 相似向量 → 同一页/相邻页 → 更少页 per query。
