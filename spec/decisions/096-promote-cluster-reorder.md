# DEC-096: Promote Within-Block Cluster Sort for Vecblock Locality
<!-- ndf: kind=decision id=DEC-096 level=3 status=accepted date=2026-08-10 -->
<!-- ndf: affects=BEH-037,API-021 depends-on=DEC-095 -->
<!-- ndf: source=poc/vecblock-cluster-reorder/ ; track=promote ; Topic: vecblock-cluster-reorder -->
<!-- ndf: Promotes: vecblock-cluster-reorder -->

## Context

VLDB 2025 论文的"空间感知插入重排"概念启发了 vecblock 聚类重排。
通过 k-means 聚类排序减少有效 I/O 页数。

## POC Evidence (R0-R2)

| 轮次 | 方案 | 256MB 1T QPS | Δ vs BFS |
|------|------|:---:|:---:|
| R0 | k=256 wb | 1,573 | +9.4% |
| R1 | Full k=512 | 1,417 | −1.5% ❌ |
| R2 | k=1024 wb | 1,775 | +23.4% |

R2 golden (4 scenes): 256MB 1T=1,775, 256MB 16T=5,253, 512MB 1T=2,198, 512MB 16T=8,987

## Decision

**Accept**: Promote within-block cluster sort (k=1024) as offline tool.

1. Cluster_reorder工具 → 
2. 无需搜索代码改动 — vecblock 格式不变，route table 不变
3. 用户可选：生成 cluster-sorted vecblock 后替换原文件

### 不要
- Full cross-block reorder (R1 −1.5%, 破坏 BFS 局部性)
- 默认开启此布局（离线选择，非运行时行为）

### 延期
- L3 semantic core: offline tool, not runtime behavior
