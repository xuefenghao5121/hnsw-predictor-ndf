# Golden Performance Baseline — Trunk 434c6f5

> 创建: 2026-08-09
> Trunk SHA: 434c6f5874a27c64c26a973f28988d90159e06a3
> 协议: CON-SLA-020 sustained, CON-SLA-014 strict cgroup, CON-SLA-019 禁预热
> 数据集: SIFT1M (M=16, EF=100)
> Query: 官方 10K pool, 15 rounds × 1000, seed=42
> 硬件: Intel i7-13700 (16C/24T), 32GB DDR4, NVMe SSD
> 每配置 3 次独立测量 (R1/R2/R3), strict cgroup drop_caches

## 金标数据

### 256MB cgroup

| 线程 | agg QPS (mean±std) | steady QPS (mean±std) | CV | Recall@10 | R1 | R2 | R3 |
|------|-------------------|----------------------|-----|----------|------|------|------|
| 1T | **1,067 ± 13** | **1,144 ± 15** | 1.2% | 97.76% | 1052/1127 | 1075/1156 | 1074/1149 |
| 16T | **2,006 ± 15** | **2,305 ± 18** | 0.8% | 97.76% | 2007/2324 | 1990/2288 | 2021/2302 |

### 512MB cgroup

| 线程 | agg QPS (mean±std) | steady QPS (mean±std) | CV | Recall@10 | R1 | R2 | R3 |
|------|-------------------|----------------------|-----|----------|------|------|------|
| 1T | **1,506 ± 15** | **1,653 ± 14** | 1.0% | 97.76% | 1488/1638 | 1513/1666 | 1515/1656 |
| 16T | **4,544 ± 90** | **5,994 ± 261** | 2.0% | 97.76% | 4525/6042 | 4465/5712 | 4642/6227 |

### SLA 合规 (CON-SLA-020)

| 配置 | SLA 阈值 | 金标 mean | 裕量 | 状态 |
|------|---------|----------|------|------|
| 256MB 1T agg | ≥ 950 | 1,067 | +12.3% | ✅ |
| 256MB 16T agg | ≥ 1,850 | 2,006 | +8.4% | ✅ |
| 512MB 1T agg | ≥ 1,350 | 1,506 | +11.6% | ✅ |
| 512MB 16T agg | ≥ 3,900 | 4,544 | +16.5% | ✅ |

## 测量环境

```
标准环境变量:
  CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
  L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
  FLAT_VEC_MB=64 REFINE_EF=100 ADAPTIVE_EF=0

数据路径:
  output/sift1m_m16/sift1m_m16_{graph,bfs,blocks_64k,route_64k,vecblocks_64k}.bin
  output/pqco_sift1m_M32_correct.bin
  data/sift_base.fvecs
  data/sift_query_official10k.fvecs
  data/sift_groundtruth_official.ivecs
```

## 使用规范

1. **POC 后更新**: 每次 promote 或 POC 验证后，用同一协议重跑 4 配置 × 3 轮
2. **A/B 对比**: 对比新旧 binary 时 MUST 在同一 session 交替跑（非跨 session）
3. **CV 阈值**: 如某配置 CV > 3%，结果不可信，需重跑
4. **回归判定**: 新版本 agg/steady 落在 golden ±2CV 内视为无回归
5. **金标更新**: promote 合入后更新本文件（新 Trunk SHA + 新数据）
