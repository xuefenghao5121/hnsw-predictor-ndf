# Golden Performance Baseline — Trunk 434c6f5

> 创建: 2026-08-09
> 更新: 2026-08-09 (补补充优化配置)
> Trunk SHA: 434c6f5874a27c64c26a973f28988d90159e06a3
> 协议: CON-SLA-020 sustained, CON-SLA-014 strict cgroup, CON-SLA-019 禁预热
> 数据集: SIFT1M (M=16/M=24, EF=100/90/60)
> Query: 官方 10K pool, 15 rounds × 1000, seed=42
> 硬件: Intel i7-13700 (16C/24T), 32GB DDR4, NVMe SSD
> 每配置 2-3 次独立测量, strict cgroup drop_caches

## 1. SLA 基线配置 (M=16, EF=100, 3 轮)

### 256MB cgroup

| 线程 | agg QPS (mean±std) | steady QPS (mean±std) | CV | Recall@10 |
|------|-------------------|----------------------|-----|----------|
| 1T | **1,067 ± 13** | **1,144 ± 15** | 1.2% | 97.76% |
| 16T | **2,006 ± 15** | **2,305 ± 18** | 0.8% | 97.76% |

### 512MB cgroup

| 线程 | agg QPS (mean±std) | steady QPS (mean±std) | CV | Recall@10 |
|------|-------------------|----------------------|-----|----------|
| 1T | **1,506 ± 15** | **1,653 ± 14** | 1.0% | 97.76% |
| 16T | **4,544 ± 90** | **5,994 ± 261** | 2.0% | 97.76% |

### SLA 合规

| 配置 | SLA 阈值 | 金标 mean | 裕量 | 状态 |
|------|---------|----------|------|------|
| 256MB 1T | ≥ 950 | 1,067 | +12.3% | ✅ |
| 256MB 16T | ≥ 1,850 | 2,006 | +8.4% | ✅ |
| 512MB 1T | ≥ 1,350 | 1,506 | +11.6% | ✅ |
| 512MB 16T | ≥ 3,900 | 4,544 | +16.5% | ✅ |

## 2. DEC-086 优化配置 (M=16, EF=90, +ADAPTIVE eef=40, 2 轮)

> 来源: sustained-param-retuning POC (promoted)
> 关联: DEC-086, ADAPTIVE_EF=1, ADAPTIVE_EASY_EF=40, ADAPTIVE_EASY_GAP=1.006

### 256MB cgroup

| 线程 | agg QPS | steady QPS | Recall@10 | vs SLA agg | vs SLA steady |
|------|---------|-----------|----------|-----------|--------------|
| 1T | **1,360** | **1,481** | 96.91% | +27.4% | +29.5% |
| 16T | **3,107** | **3,546** | 96.91% | +54.9% | +53.9% |

### 512MB cgroup

| 线程 | agg QPS | steady QPS | Recall@10 | vs SLA agg | vs SLA steady |
|------|---------|-----------|----------|-----------|--------------|
| 1T | **1,808** | **2,047** | 96.91% | +20.1% | +23.8% |
| 16T | **6,366** | **10,235** | 96.91% | +40.1% | +70.8% |

## 3. DEC-087 Pareto 最优配置 (M=24, EF=60, BASE, 2 轮)

> 来源: pipeline-param-retuning POC (promoted)
> 关联: DEC-087, M_graph=24, EF=60, ADAPTIVE_EF=0
> 数据: output/sift1m_m24/

### 256MB cgroup

| 线程 | agg QPS | steady QPS | Recall@10 | vs SLA agg | vs SLA steady |
|------|---------|-----------|----------|-----------|--------------|
| 1T | **1,450** | **1,702** | 96.60% | +35.9% | +48.8% |
| 16T | **3,649** | **4,827** | 96.60% | +81.9% | +109.4% |

### 512MB cgroup

| 线程 | agg QPS | steady QPS | Recall@10 | vs SLA agg | vs SLA steady |
|------|---------|-----------|----------|-----------|--------------|
| 1T | **1,991** | **2,282** | 96.60% | +32.3% | +38.1% |
| 16T | **7,644** | **13,085** | 96.60% | +68.2% | +118.3% |

## 4. 三配置横向对比 (agg QPS)

| Config | 256MB 1T | 256MB 16T | 512MB 1T | 512MB 16T |
|--------|----------|-----------|----------|-----------|
| M=16 EF=100 (SLA) | 1,067 | 2,006 | 1,506 | 4,544 |
| M=16 EF=90 +ADAPT | 1,360 (+27%) | 3,107 (+55%) | 1,808 (+20%) | 6,366 (+40%) |
| M=24 EF=60 | 1,450 (+36%) | 3,649 (+82%) | 1,991 (+32%) | 7,644 (+68%) |

**M=24 EF=60 是全场景最优配置，在 recall ≥ 96.60% 约束下 QPS 提升 32-82%。**

## 测量环境

```
标准环境变量:
  CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
  L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
  FLAT_VEC_MB=64

EF=100 配置: REFINE_EF=100 ADAPTIVE_EF=0
EF=90 配置:  REFINE_EF=90  ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=40 ADAPTIVE_EASY_GAP=1.006
EF=60 配置:  REFINE_EF=60  ADAPTIVE_EF=0 (M=24 graph)
```

## 使用规范

1. **POC 后更新**: 每次 promote 或 POC 验证后，用同一协议重跑全部三组配置
2. **A/B 对比**: 对比新旧 binary 时 MUST 在同一 session 交替跑（非跨 session）
3. **CV 阈值**: 如某配置 CV > 3%，结果不可信，需重跑
4. **回归判定**: 新版本 agg/steady 落在 golden ±2CV 内视为无回归
5. **金标更新**: promote 合入后更新本文件（新 Trunk SHA + 新数据）
6. **脚本**: `sudo bash scripts/run_golden.sh` 跑 SLA 基线 (EF=100)

## 原始数据

详见 `/tmp/golden/*.log`（每轮完整 CSV_ROW + CSV_AGG）
