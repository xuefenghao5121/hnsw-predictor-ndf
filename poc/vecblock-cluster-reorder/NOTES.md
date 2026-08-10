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

## R0 结果: within-block cluster sort, k=256 (2026-08-10)

### 方法

1. 从 vecblock 文件直接提取 1,000,000 个向量
2. k-means (k=256, 20 iters, 34.9s) 聚类
3. 每个 64KB block 内按 cluster ID 重新排序向量 + node_ids
4. 保留 block 边界不变 → route table 不变 → 直接替换 vecblock 文件

### k-means 统计

- Cluster sizes: min=1094, max=9603, avg=3906
- 254,184 cluster switches across 7937 blocks (avg ~32/block)
- 每 block 128 vectors, 平均每 cluster 约4个 vector per block

### A/B 结果 (1T, 256MB, Config C)

| 路径 | BFS (baseline) | Cluster k=256 | Delta | Profile 变化 |
|------|:---:|:---:|:---:|------|
| **pread** (default) | 1,438 | **1,573** | **+9.4%** | pread: 407us→345us (−15%) |
| **CQE peeking** | 1,463 | **1,587** | **+8.5%** | io_rest: 242us→199us (−18%) |
| recall | 96.60% | 96.60% | 0 ✅ | — |

### Profile Comparison

| | BFS pread | Cluster pread | BFS CQE | Cluster CQE |
|--|:---:|:---:|:---:|:---:|
| pread / io_rest | 407us | **345us** | 242us | **199us** |
| pages/query | 44.6 | 45.1 | 44.6 | 45.1 |
| cached | 17.6 | 17.6 | 17.6 | 17.6 |
| rerank/compute | 7us | 6us | 1us | 1us |

### 分析

1. **I/O 时间显著减少**: pread −15% (62us), io_rest −18% (43us)
2. **页数基本不变** (+0.5 pages): 说明不是减少页数，而是提升页质量
3. **根因**: 块内 cluster sort →
   - 同 cluster 向量集中在连续页面
   - 内核 readahead 更有效（相邻页更可能被同一查询需要）
   - page cache 局部性改善（相似向量 → 更高概率已预热）

4. **与 CQE peeking 复合**: 两个优化独立有效
   - cluster sort: I/O 更快（readahead 效率）
   - CQE peeking: 完成顺序处理（消除屏障）
   - 复合收益: 1,438 → 1,587 (+10.3%)

5. **收益独立于 CQE peeking**: pread 路径 +9.4%, CQE 路径 +8.5%

### 结论

Within-block cluster sort (k=256) **正向 +9.4% (pread) / +8.5% (CQE peeking)**。
方向 B R0 正向 ✅

### 下一步

- R1: k=512/1024 更大聚类数（更高精度 → 更好局部性？）
- R1: 全量聚类重排（跨 block 重分配，最大化聚类局部性）
- R1: 多维 scaling (4T/16T)


## R1 结果: 全量聚类重排 k=512 (2026-08-10)

### 方法

替换 within-block sort 为全局 cluster 重排（跨 block 分配 cluster）：
1. 按 cluster ID 全局排序所有 vector
2. 顺序写入新 vecblock（每 block = 连续 cluster 的 vectors）
3. 重建 route table（node_id → new_block_id）

### 结果（金标协议，4 场景）

| 场景 | BFS baseline | Full cluster k=512 | Within-block k=256 |
|------|:---:|:---:|:---:|
| 256MB 1T | 1,438 | **1,417 (−1.5%)** ❌ | 1,573 (+9.4%) ✅ |
| 256MB 16T | 3,483 | N/A | — |
| 512MB 1T | — | 673 ❌ | — |
| 512MB 16T | — | 9,179 | — |

### 根因分析

全量 cluster 重排破坏 BFS 遍历顺序 → HNSW graph traversal 的局部性丧失。
BFS 顺序保证 graph neighbors 在相邻 block → 全量重排把 neighbors 分散到不同 cluster → 更多随机 I/O。

within-block 正确：保留 BFS 块级结构 + 块内 cluster 局部性 → +9.4%。

### 结论

**全量聚类重排 = 负结果 ❌**
**Within-block cluster sort = 正向 +9.4% ✅**

方向 B 最佳方案: within-block cluster sort (k=256)。

## R2 结果: within-block k=1024 + golden protocol (2026-08-10)

### 方法

k-means with k=1024, within-block cluster sort (同 R0 方法，仅 k 不同)。

### k-means stats

- k=1024, 20 iters, 124.3s
- Cluster sizes: min=265 max=3894 avg=977
- 432,443 cluster switches (1.7x k=256 的 254K)

### 金标结果（4 场景, sustained, strict cgroup, 禁预热）

| 场景 | BFS baseline | k=256 wb | k=1024 wb | Δ vs BFS | Δ vs k=256 |
|------|:---:|:---:|:---:|:---:|:---:|
| 256MB 1T | 1,438 | 1,573 | **1,775** | **+23.4%** | +12.8% |
| 256MB 16T | 3,483 | — | **5,253** | **+50.8%** | — |
| 512MB 1T | — | — | **2,198** | — | — |
| 512MB 16T | — | — | **8,987** | — | — |

### 分析

1. **k=1024 >> k=256**: 更大 k = 更紧致 cluster = 更相似的向量在每页 = 更好的局部性
2. **16T 收益放大**: 50.8% vs BFS（多线程并行 I/O × cluster 局部性 = 超线性？）
3. **256→512MB**: 1T 2,198/1,775=1.24×, 16T 8,987/5,253=1.71×
4. **更多 cluster switches ≠ 更差**: 432K vs 254K switches，但每 cluster 更紧致 → 每页价值更高

### 结论

**Within-block cluster sort k=1024 = +23.4% @1T, +50.8% @16T** ✅✅
k=1024 是当前最优配置。值得 promote。

## R2 Profile: k=1024 CQE peeking vs pread (2026-08-10)

| 路径 | k=1024 QPS | BFS QPS | Profile CQE: io_rest |
|------|:---:|:---:|:---:|
| pread | 1,748 | 1,438 | pread time: — |
| CQE peeking | 1,708 | 1,463 | **144us** (BFS: 242us, −40%) |

CQE peeking + cluster k=1024: io_rest 从 242us → 144us (−40%)。
Cluster 局部性使 CQE 先到达的页面包含更相似向量 → 搜索空间更快收窄。

pread vs CQE 在 k=1024 下接近（1,748 vs 1,708），可能 CQE 的 page→cands 索引开销随页数不降而 offset。
推荐：按用户场景选择 pread (纯 cluster) 或 CQE (cluster + CQE)。
