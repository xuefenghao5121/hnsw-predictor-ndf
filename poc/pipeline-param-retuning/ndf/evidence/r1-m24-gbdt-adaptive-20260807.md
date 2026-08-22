> ⚠️ **白嫖数据 — 不合 CON-SLA-014，不可作为 promote 依据**。仅供趋势参考。
# R1: M=24 GBDT 重训练 + ADAPTIVE/BASE 三模式对比

> 日期：2026-08-07
> Trunk: c63694f
> 协议：CON-SLA-020 (sustained, N=1000, R=15, seed=42)
> 图: M=24 (output/sift1m_m24/)
> PQ: M_pq=32 (不变)

## GBDT 模型

- 训练数据: M=24 图上 10K 官方 query pool, PROFILE_LLSP 采集
- Label: min_n (包含全部 top-10 的最小候选数)
- Label stats: median=22 (vs M=16 median ~30)
- Val MAE: 15.16

## 完整结果

### BASE 模式 (无 GBDT, 无 ADAPTIVE)

| Phase A ef | Agg QPS | Steady QPS | Recall | RSS |
|-----------|---------|-----------|--------|-----|
| 60 | 3492 | 3531 | 96.60% | 230 |
| 80 | 2820 | 2837 | 97.97% | 230 |
| 100 | 2362 | 2386 | 98.67% | 230 |
| 120 | 1993 | 2018 | 99.04% | 230 |

### ADAPTIVE 模式 (EF=60, easy=40, hard=100)

| Config | Agg QPS | Steady QPS | Recall | RSS |
|--------|---------|-----------|--------|-----|
| EF=60, EASY=40 | 3595 | 3633 | 96.22% | 230 |

### GBDT 模式 (M=24-trained, margin=1.0)

| Phase A ef | REFINE_EF | Agg QPS | Steady QPS | Recall | RSS |
|-----------|-----------|---------|-----------|--------|-----|
| 60 | 60 | 3570 | 3601 | 96.46% | 230 |
| 80 | 80 | 3055 | 3079 | 97.53% | 230 |
| 200 | 200 | 1754 | 1760 | 96.15% | 230 |

### GBDT margin 扫描 (ef=200, REFINE_EF=200)

| margin | Agg QPS | Recall |
|--------|---------|--------|
| 0.8 | 1788 | 93.21% ❌ |
| 1.0 | 1754 | 96.15% ✅ |
| 1.2 | 1742 | 97.60% ✅ |
| 1.5 | 1704 | 98.73% ✅ |

## 核心发现

### 1. GBDT 必须配合低 Phase A ef

GBDT ef=200 QPS=1754 vs GBDT ef=60 QPS=3570 — 2x 差距。
原因: Phase A 粗筛 (PQ ADC scan) 的计算量正比于 ef_coarse。
GBDT 只影响 Phase B 候选截断, 不减少 Phase A 计算量。
**必须同时设 benchmark ef + REFINE_EF = 目标值。**

### 2. M=24 最优配置

| 场景 | 最优 | QPS | Recall |
|------|------|-----|--------|
| 最大化 QPS, recall ≥ 95% | **BASE EF=60** | **3492** | 96.60% |
| 平衡 QPS + recall | **GBDT EF=80 margin=1.0** | **3055** | 97.53% |
| 最大化 QPS via adaptive | ADAPTIVE EF=60 | 3595 | 96.22% |

### 3. GBDT vs ADAPTIVE vs BASE

在 ef=60 下三者差异很小 (3492-3595 QPS)。
GBDT 在 ef=80 下比 BASE +8.3% QPS。
GBDT 的价值在更高 ef 下更显著（per-query 截断收益更大）。

### 4. M=24 GBDT label 特征

median min_n = 22 (vs M=16 ~30)
→ M=24 图更连通, top-K 更集中
→ GBDT 更难预测 (variance 更大)
→ MAE 15.16 偏高
