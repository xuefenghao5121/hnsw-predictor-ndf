# Baseline: bl-trunk-golden-434c6f5

> baseline_id: bl-trunk-golden-434c6f5  
> trunk_sha: 434c6f5874a27c64c26a973f28988d90159e06a3  
> short_sha: 434c6f5  
> status: superseded  
> measured: 2026-08-09  
> protocol: [[CON-SLA-020]] sustained, [[CON-SLA-014]] strict cgroup, [[CON-SLA-019]] 禁预热  
> dataset: SIFT1M  
> query: 官方 10K pool, 15 rounds × 1000, seed=42  
> hardware: Intel i7-13700 (16C/24T), 32GB DDR4, NVMe SSD  
> configs: cfg-sla-ef100, cfg-adaptive-ef90, cfg-m24-ef60  
> clause: [[CON-GOLDEN-001]]  
> process: [[META-006]]

> 迁移自原 `golden-baseline.md` 正文（数字未改）。新 Trunk 金标 MUST bump 新 `bl-trunk-golden-<shortsha>`，
> 不可原地偷改本 id 的数字给仍引用旧卡的主题用。

## 1. cfg-sla-ef100 (M=16, EF=100, 3 轮)

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

### SLA 合规（合约下限对照，非本卡数字源）

| 配置 | SLA 阈值 | 金标 mean | 裕量 | 状态 |
|------|---------|----------|------|------|
| 256MB 1T | ≥ 950 | 1,067 | +12.3% | OK |
| 256MB 16T | ≥ 1,850 | 2,006 | +8.4% | OK |
| 512MB 1T | ≥ 1,350 | 1,506 | +11.6% | OK |
| 512MB 16T | ≥ 3,900 | 4,544 | +16.5% | OK |

## 2. cfg-adaptive-ef90 (M=16, EF=90 +ADAPTIVE, 2 轮)

> 来源: sustained-param-retuning POC (promoted)；[[DEC-086]]

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

## 3. cfg-m24-ef60 (M=24, EF=60, 2 轮)

> 来源: pipeline-param-retuning POC (promoted)；[[DEC-087]]；数据 `output/sift1m_m24/`

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
| cfg-sla-ef100 | 1,067 | 2,006 | 1,506 | 4,544 |
| cfg-adaptive-ef90 | 1,360 (+27%) | 3,107 (+55%) | 1,808 (+20%) | 6,366 (+40%) |
| cfg-m24-ef60 | 1,450 (+36%) | 3,649 (+82%) | 1,991 (+32%) | 7,644 (+68%) |

## 回归判定（对照本卡）

- agg/steady 落在金标 ±2CV 内 = 无回归
- Recall 下降 > 0.3pp = 回归
- CV > 3% = 结果不可信，需重跑

## 脚本

`sudo bash scripts/run_golden.sh`（配置 A / cfg-sla-ef100 自动化）
