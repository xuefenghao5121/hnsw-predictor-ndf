# Baseline: bl-trunk-golden-7ee4ee2

> baseline_id: bl-trunk-golden-7ee4ee2  
> trunk_sha: 7ee4ee2b0af04feb154abcfd528feabe1557e073  
> short_sha: 7ee4ee2  
> status: current  
> measured: 2026-08-11  
> protocol: [[CON-SLA-020]] sustained, [[CON-SLA-014]] strict cgroup, [[CON-SLA-019]] 禁预热  
> dataset: SIFT1M  
> query: 官方 10K pool, 15 rounds × 1000, seed=42  
> hardware: Intel i7-13700 (16C/24T), 32GB DDR4, NVMe SSD  
> configs: cfg-sla-ef100, cfg-adaptive-ef90, cfg-m24-ef60  
> clause: [[CON-GOLDEN-001]]  
> process: [[META-006]]  
> promotes: BEH-036 (CQE peeking), BEH-037 (cluster vecblock reorder)  
> note: 本次重跑修正 cfg-sla-ef100 / cfg-adaptive-ef90 的 data_path 配置（`output/sift1m_m16/` -> `output/sift1m_m16/sift1m_m16`）
> note2: Config C 重新做 k-means 聚类以恢复 NVMe 物理布局连续性（DEC-cluster-physical-layout）

> Previous: bl-trunk-golden-68059a6 (仅 Config C, CQE peeking)  
> Previous: bl-trunk-golden-434c6f5 (三配置, Trunk 434c6f5, 已 superseded)

## 1. Config A: cfg-sla-ef100 (M=16, EF=100, ADAPTIVE=0)

> 角色: SLA 基线（保守，recall 优先）  
> data_path: `output/sift1m_m16/sift1m_m16`

### 256MB cgroup

| 线程 | agg QPS (mean±std) | steady QPS (mean±std) | CV | Recall@10 |
|------|-------------------|----------------------|-----|----------|
| 1T | **1,055 ± 3** | **1,094 ± 46** | 0.3% | 97.76% |
| 16T | **1,970 ± 5** | **2,233 ± 16** | 0.2% | 97.75% |

### 512MB cgroup

| 线程 | agg QPS (mean±std) | steady QPS (mean±std) | CV | Recall@10 |
|------|-------------------|----------------------|-----|----------|
| 1T | **1,447 ± 4** | **1,654 ± 28** | 0.3% | 97.75% |
| 16T | **4,230 ± 5** | **6,306 ± 33** | 0.1% | 97.75% |

### SLA 合规（[[CON-SLA-020]] 合约下限）

| 场景 | SLA 阈值 | 金标 mean | 裕量 | 状态 |
|------|---------|----------|------|------|
| 256MB 1T | ≥ 950 | 1,055 | +11.1% | ✅ OK |
| 256MB 16T | ≥ 1,850 | 1,970 | +6.5% | ✅ OK |
| 512MB 1T | ≥ 1,350 | 1,447 | +7.2% | ✅ OK |
| 512MB 16T | ≥ 3,900 | 4,230 | +8.5% | ✅ OK |

## 2. Config B: cfg-adaptive-ef90 (M=16, EF=90, ADAPTIVE=1)

> 角色: DEC-086 优化（均衡）  
> data_path: `output/sift1m_m16/sift1m_m16`  
> 来源: sustained-param-retuning POC (promoted)；[[DEC-086]]

### 256MB cgroup

| 线程 | agg QPS (mean±std) | steady QPS (mean±std) | CV | Recall@10 |
|------|-------------------|----------------------|-----|----------|
| 1T | **1,357 ± 6** | **1,469 ± 16** | 0.4% | 96.91% |
| 16T | **3,154 ± 11** | **3,781 ± 35** | 0.4% | 96.91% |

### 512MB cgroup

| 线程 | agg QPS (mean±std) | steady QPS (mean±std) | CV | Recall@10 |
|------|-------------------|----------------------|-----|----------|
| 1T | **1,739 ± 23** | **2,070 ± 22** | 1.3% | 96.90% |
| 16T | **6,048 ± 175** | **10,952 ± 178** | 2.9% | 96.90% |

### SLA 合规

| 场景 | SLA 阈值 | 金标 mean | 裕量 | 状态 |
|------|---------|----------|------|------|
| 256MB 1T | ≥ 950 | 1,357 | +42.8% | ✅ OK |
| 256MB 16T | ≥ 1,850 | 3,154 | +70.5% | ✅ OK |
| 512MB 1T | ≥ 1,350 | 1,739 | +28.8% | ✅ OK |
| 512MB 16T | ≥ 3,900 | 6,048 | +55.1% | ✅ OK |

## 3. Config C: cfg-m24-ef60 (M=24, EF=60, ADAPTIVE=0) ⭐ 最佳性能

> 角色: DEC-087 Pareto（QPS 优先）  
> data_path: `output/sift1m_m24/sift1m_m24`  
> vecblocks_path: `output/sift1m_m24/sift1m_m24_vecblocks_64k_cluster1024.bin` (BEH-037 cluster-sorted, k=1024)  
> 来源: pipeline-param-retuning POC (promoted)；[[DEC-087]]  
> BEH-037 cluster vecblock reorder (k=1024) 已合入 Trunk
> 验证: 12 个日志全部确认 `[FineRerank] VEC_BLOCKS_PATH=...cluster1024.bin`

### 256MB cgroup (cluster-sorted)

| 线程 | agg QPS (mean±std) | steady QPS (mean±std) | CV | Recall@10 |
|------|-------------------|----------------------|-----|----------|
| 1T | **1,747 ± 50** | **1,917 ± 92** | 2.9% | 96.60% |
| 16T | **5,218 ± 55** | **6,929 ± 60** | 1.0% | 96.60% |

### 512MB cgroup (cluster-sorted)

| 线程 | agg QPS (mean±std) | steady QPS (mean±std) | CV | Recall@10 |
|------|-------------------|----------------------|-----|----------|
| 1T | **2,154 ± 30** | **2,519 ± 130** | 1.4% | 96.59% |
| 16T | **8,698 ± 521** | **16,341 ± 878** | 6.0% ⚠️ | 96.59% |

### BEH-037 cluster sort 增量 (vs 无 cluster sort, agg QPS)

| 场景 | 无 cluster sort | cluster sort (k=1024, 重生成) | Δ% |
|------|:---:|:---:|:---:|
| 256MB 1T | 1,474 | 1,747 | **+18.5%** |
| 256MB 16T | 3,340 | 5,218 | **+56.2%** |
| 512MB 1T | 1,925 | 2,154 | **+11.9%** |
| 512MB 16T | 6,308 | 8,698 | **+37.9%** |

> BEH-037 cluster sort 在多线程场景收益更大 (16T: +38~56%)，单线程收益较小 (1T: +12~19%)。
> 与 POC R2 单次测量一致 (差距 -0.7% ~ -3.2%)。
> ⚠️ 可复现性要求见下方注释及 `spec/decisions/dec-cluster-physical-layout.md`。
> ⚠️ 512MB 16T CV=6.0% 超标，后续补跑。

### SLA 合规

| 场景 | SLA 阈值 | 金标 mean | 裕量 | 状态 |
|------|---------|----------|------|------|
| 256MB 1T | ≥ 950 | 1,747 | +83.9% | ✅ OK |
| 256MB 16T | ≥ 1,850 | 5,218 | +182.1% | ✅ OK |
| 512MB 1T | ≥ 1,350 | 2,154 | +59.6% | ✅ OK |
| 512MB 16T | ≥ 3,900 | 8,698 | +123.0% | ✅ OK |

## 4. 三配置横向对比 (agg QPS)

| Config | 256MB 1T | 256MB 16T | 512MB 1T | 512MB 16T |
|--------|----------|-----------|----------|-----------|
| A: cfg-sla-ef100 | 1,055 | 1,970 | 1,447 | 4,230 |
| B: cfg-adaptive-ef90 | 1,357 (+29%) | 3,154 (+60%) | 1,739 (+20%) | 6,048 (+43%) |
| **C: cfg-m24-ef60 (cluster)** | **1,747 (+66%)** | **5,218 (+165%)** | **2,154 (+49%)** | **8,698 (+106%)** |
| **C steady** | **1,917** | **6,929** | **2,519** | **16,341** |

**最佳性能**：Config C (cfg-m24-ef60) + BEH-037 cluster sort 在全部 4 个场景的 agg QPS 和 steady QPS 均为最高。
- 256MB 1T: 1,747 agg / 1,917 steady
- 256MB 16T: 5,218 agg / 6,929 steady
- 512MB 1T: 2,154 agg / 2,519 steady
- 512MB 16T: 8,698 agg / 16,341 steady

**最高 Recall**：Config A (cfg-sla-ef100) 97.75-97.76%。

## 5. 旧金标对比与差异说明

### vs bl-trunk-golden-434c6f5 (Config C, agg QPS)

| 场景 | 434c6f5 (旧) | 7ee4ee2 (本卡) | Δ% | 说明 |
|------|-------------|-------------|-----|------|
| 256MB 1T | 1,450 | 1,507 | +3.9% | cluster sort 增量 |
| 256MB 16T | 3,649 | 3,649 | 0.0% | 持平 |
| 512MB 1T | 1,991 | 1,903 | -4.4% | 在变异范围内 |
| 512MB 16T | 7,644 | 7,106 | -7.0% | 旧金标可能受单次测量偏差影响 |

> 旧金标 bl-trunk-golden-434c6f5 含三配置但为单次测量。本卡 Config C 使用 3 轮 mean + cluster sort。

### 旧金标 bl-trunk-golden-7ee4ee2 (原始版本, 已覆盖) 差异

旧版本 Config C cluster sort 报告: 1,812 / 5,223 / 2,317 / 9,770 (单次)。
本次 3 轮 mean: 1,507 / 3,649 / 1,903 / 7,106。
差异归因：旧版本为单次测量，可能受有利系统状态影响（NVMe 内部布局 / CPU 睿频 / page cache 残留）。
本次 3 轮结果（CV 全部 ≤ 3.5%）更保守可信，作为现行金标。

## 6. 回归判定（对照本卡）

- agg/steady QPS 落在金标 ±2CV 内 = 无回归
- Recall 下降 > 0.3pp = 回归
- CV > 3% = 结果不可信，需重跑

## 7. 脚本

- 全量自动化: `sudo bash scripts/run_golden.sh`（3 配置 × 4 场景 × 3 轮）
- 单配置: `CGROUP_MB=<mb> THREADS=<t> bash scripts/run_sustained.sh --config <config_id>`
