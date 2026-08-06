# R6: hnswlib 对照（官方 query 池）

> 日期: 2026-08-06
> Topic: sustained-query-benchmark
> 数据: 官方 SIFT 10K query + 官方 GT (k=10)

## 配置

hnswlib unlimited memory（in-memory 天花板），EF=100，每组前 `drop_caches`。

索引：`output/sift1m_index.bin`
GT：`data/sift_gt_official10k_k10.bin`（官方 ivecs 转 k=10 内部格式）

## 结果

| 线程 | QPS | Recall@10 | RSS |
|------|-----|----------|-----|
| 1T | 6,423.6 | 98.25% | 734 MB |
| 4T | 22,757.0 | 98.25% | 739 MB |
| 16T | 42,947.1 | 98.25% | 763 MB |

## hnswlib recall 的三次修正

| 测量 | Recall | 有效性 |
|------|--------|--------|
| base-sampled 10Kq + 含 self GT | 99.47% | ❌ GT 含 self-match，白送 ~10% |
| base-sampled 10Kq + 排除 self GT | 89.90% | ❌ query 分布非标准（从 base 抽样） |
| **官方 10Kq + 官方 GT** | **98.25%** | ✅ |

98.25% 是 hnswlib 在标准 SIFT 上的真实 recall，符合文献预期
（EF=100, M=16 量级的典型值）。

之前 89.90% 的异常低值，根因是 base-sampled query 的近邻结构与标准 query
不同：从 base 抽的向量位于数据流形内部，其真实 10-NN 更密集难分，
在同 EF 下更难召回。

## DiskHNSW vs hnswlib（sustained，官方池）

| 线程 | DiskHNSW 512MB 稳态 | hnswlib unlimited | 比例 | DiskHNSW recall | hnswlib recall |
|------|-------------------|------------------|------|----------------|---------------|
| 1T | 1,729 | 6,424 | 26.9% | 96.00% | 98.25% |
| 4T | 5,247 | 22,757 | 23.1% | 96.00% | 98.25% |
| 16T | 6,694 | 42,947 | 15.6% | 96.00% | 98.25% |

| 线程 | DiskHNSW 256MB 稳态 | hnswlib | 比例 |
|------|-------------------|---------|------|
| 1T | 1,174 | 6,424 | 18.3% |
| 4T | 2,519 | 22,757 | 11.1% |
| 16T | 2,456 | 42,947 | 5.7% |

### QPS/MB 内存效率（sustained）

以 cgroup 预算 vs hnswlib RSS 计（[[CON-HONEST-002]] 口径）：

| 配置 | 稳态 QPS | 内存 | QPS/MB | vs hnswlib |
|------|---------|------|--------|-----------|
| hnswlib 16T | 42,947 | 763 MB | 56.3 | 1.00× |
| DiskHNSW 512MB 16T | 6,694 | 512 MB | 13.1 | 0.23× |
| DiskHNSW 256MB 16T | 2,456 | 256 MB | 9.6 | 0.17× |
| DiskHNSW 512MB 16T + ADAPTIVE | 9,560 | 512 MB | 18.7 | 0.33× |

**诚实结论**：在 sustained I/O bound 场景下，DiskHNSW 的 QPS/MB
**不再优于** hnswlib。此前声称的 1.10×/1.36× 优势来自 cache-warmed 测量。

DiskHNSW 的真实价值定位应修正为：
- **能在内存预算不足时工作**（hnswlib 在 DEEP10M 直接 OOM）
- **绝对内存占用低**（256MB vs 763MB = 33%）
- 但**吞吐代价显著**（5.7–26.9% of hnswlib）

这是一个 trade-off，不是全面胜出。

## R6 验收

| 检查项 | 结果 |
|--------|------|
| hnswlib recall 合理 | ✅ 98.25%（符合文献） |
| 同 GT 下双方可比 | ✅ 均用官方 GT |
| Pareto 对照完整 | ✅ 1/4/16T × 512/256MB |
