# BEH-037: Cluster-Sorted Vecblock Layout — Improved I/O Locality
<!-- ndf: kind=clause id=BEH-037 level=1 status=stable -->
<!-- ndf: depends-on=API-021 trunk-ref=dc56969 -->
<!-- ndf: source=poc/vecblock-cluster-reorder/ ; track=promote ; Topic: vecblock-cluster-reorder -->

## Behavior

Vecblock 文件中的向量可按 k-means 聚类在**块内**重新排序：

1. 对 SIFT1M 向量做 k-means 聚类（k=1024）
2. 每个 64KB block 内按 cluster ID 排序向量 + node_ids
3. **保留 block 边界不变** — route table 不变，搜索代码零改动
4. 结果：每个 block 内相似向量集中在连续页面

### 效果

- pread 路径: I/O 时间 407→345us (−15%), QPS **+23.4%** @1T
- CQE peeking 路径: io_rest 242→144us (−40%), QPS **+16.7%** @1T
- 16T 收益放大: **+50.8%** (5,253 vs 3,483 QPS)
- Recall 不变 (96.60%)

## 使用方法

```bash
# 1. 构建工具
make cluster_reorder

# 2. 生成 cluster-sorted vecblocks
build/cluster_reorder 128 \
  output/sift1m_m24/sift1m_m24_vecblocks_64k.bin \
  output/sift1m_m24/sift1m_m24_cluster_k1024_vecblocks_64k.bin \
  1024

# 3. 替换 vecblocks 文件即可（同名替换或 DATA_PREFIX 指向新文件）
```

## Rationale

POC vecblock-cluster-reorder R0-R2 证据：
- R0: k=256 within-block +9.4% @1T
- R1: full cross-block reorder −1.5% (排除)
- R2: k=1024 within-block +23.4% @1T, +50.8% @16T

See: `spec/open/proposal-promote-cluster-reorder.md`
