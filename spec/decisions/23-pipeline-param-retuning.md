# DEC-087: Pipeline 参数调优结论 (256MB sustained) {#DEC-087}

> date: 2026-08-08
> affects: API-011, API-017
> topic: pipeline-param-retuning (promoted)
<!-- ndf: kind=decision status=stable date=2026-08-08 affects=API-011,API-017 source=observed -->
<!-- ndf: depends-on=DEC-086,CON-SLA-020 -->
<!-- ndf: promotes=pipeline-param-retuning -->

## Context

[[DEC-086]] 确定了 sustained 口径下的最优参数（EF=90 + ADAPTIVE eef=40）。
本决策在 DEC-086 基础上进一步探索 M_graph、PQ M、block size 的联合调优，
并在 256MB cgroup + CON-SLA-020 金标配置下验证。

## 实验

POC `poc/pipeline-param-retuning/` 完成 R0'-R6 全扫描（CON-SLA-014 严格隔离 + CON-SLA-019 禁预热）：

- R0': M_graph={16,24,32,48} × EF={60,80,100,120} 1T (16 configs)
- R1': GBDT/ADAPTIVE (3 configs)
- R2': PQ M={16,32,64} scan
- R3': 多线程 4/8/16T (12 configs)
- R4': Block size={32K,64K,128K} scan
- R5.1: EF 细扫 {65,70,75} + M=24 EF={50,55}
- R5.2: M=16 EF=65 ADAPTIVE + 多线程
- R6: GBDT-v3 重训（负结果）

基线验证：M=16 EF=100 1T 实测 agg=1,081 vs CON-SLA-020 的 1,076（差 0.5%）✅

## 结论

### 1. M=16 EF=65 是 256MB BASE 模式 Pareto 最优

| Config | 1T Agg QPS | 16T Agg QPS | Recall | vs 旧默认 |
|--------|-----------|------------|--------|----------|
| **M=16 EF=65** | **2,483** | **3,170** | **95.52%** | **+127%** |
| M=24 EF=60 | 1,510 | 3,471 | 96.60% | +39.6% |
| M=16 EF=100 (旧默认) | 1,092 | - | 97.76% | baseline |

M=16（Trunk 默认）在低 EF 区间全面优于 M=24。原因：M=16 CSR 更小（80MB vs 120MB），
留给 page cache 的预算更多，支持更低的 EF。

### 2. ADAPTIVE 增益与 recall 余量强相关

| Config | Recall 余量 | ADAPTIVE 增益 (1T) |
|--------|-----------|-------------------|
| M=24 EF=60 | 1.60pp | +68% |
| M=16 EF=90 (DEC-086) | 1.00pp | +16% |
| M=16 EF=65 | 0.52pp | +3-7% |

余量越大，ADAPTIVE 降 easy_ef 的空间越大。M=16 EF=65 余量仅 0.52pp，eef=35/30 不达标。

### 3. M=16 EF=65 +ADAPTIVE 16T 最高吞吐

agg=4,057 QPS, recall=95.17%。但 recall 余量紧，适合追求极致 QPS 的场景。

### 4. PQ M=32 仍是唯一选择

| PQ M | Recall | 达标 |
|------|--------|------|
| 16 | 91.60% | ❌ |
| **32** | **96.60%** | **✅** |
| 64 | 97.41% | ✅ but QPS -31% |

### 5. Block size 32K 显著优于 64K（延期）

32K vs 64K: +52.5% QPS, recall 不变。但改变 block size 需重建 pipeline Step 4-5，
延期为独立 POC 验证。

### 6. GBDT-v3 重训负结果

用官方 10K query 池 + 目标 EF 值重新 profiling + 训练 LightGBM 模型。
新模型 MAE 13.4（远优于旧模型 46.3），但在 256MB + 低 EF 下：
- M=16 EF=65: GBDT ≈ BASE (±2%)，无法有效减少候选数
- M=24 EF=60: margin=1.0 recall=94.38% (不达标)，margin=1.3 达标但 QPS < ADAPTIVE

根因：EF=65/60 候选集仅 65/60 个，60%+ query 需要 ≥50 候选，GBDT 节省空间极小。

### 不改的参数

- `M_graph=16`: Trunk 默认已正确
- `M_pq=32`: 唯一达标选择
- `REFINE_EF=200` (Trunk 默认): 不变，推荐值见 API-011
- `FLAT_VEC_MB=64` (256MB): 不变

## source

> source: poc/pipeline-param-retuning/ndf/TOPIC.md ; evidence/r0-r4-redo-20260808.md
> track: promote ; Topic: pipeline-param-retuning
