# API-021: cluster_reorder — K-Means Vecblock Cluster Sort Tool
<!-- ndf: kind=clause id=API-021 level=2 status=stable -->
<!-- ndf: depends-on=BEH-037 trunk-ref=dc56969 -->
<!-- ndf: source=poc/vecblock-cluster-reorder/ ; track=promote ; Topic: vecblock-cluster-reorder -->

## CLI

```
build/cluster_reorder <dim> <in_vecblocks> <out_vecblocks> <k>
```

| 参数 | 类型 | 说明 |
|------|------|------|
| dim | int | 向量维度 (SIFT=128) |
| in_vecblocks | path | 现有 vecblocks 文件 (64KB block 格式) |
| out_vecblocks | path | 输出 cluster-sorted vecblocks 文件 |
| k | int | k-means 聚类数 (推荐 1024) |

## 输出

1. `out_vecblocks`: 与输入同格式的 vecblock 文件，块内向量按 cluster 排序
2. stderr: k-means 迭代进度 + cluster 大小统计 + block 处理进度

## 约束

- 仅 modifies 块内向量顺序，不改变 block 边界 → route table 不变
- 需要 `-fopenmp` 编译支持（多线程 k-means）
- k 越大 → 聚类越紧致 → I/O 局部性越好 → 但 k-means 时间越长
