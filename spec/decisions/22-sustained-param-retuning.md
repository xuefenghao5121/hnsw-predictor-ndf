# DEC-086: Sustained 口径下主线调参结论 {#DEC-086}
<!-- ndf: kind=decision status=stable date=2026-08-07 affects=API-011,API-017 source=observed -->
<!-- ndf: depends-on=DEC-084 -->
<!-- ndf: promotes=sustained-param-retuning -->


> date: 2026-08-07
> affects: API-011, API-017, DEC-072, DEC-073, DEC-080
> topic: sustained-param-retuning (promoted)

## Context

[[DEC-084]] 确立 sustained 为权威口径。但所有主线参数最优值（除 GBDT_MARGIN）均来自
200q cache-warmed 口径。本决策记录 sustained 下的重新调参结论。

## 实验

POC `poc/sustained-param-retuning/` 完成 R0-R4 全扫描：

- R0: REFINE_EF {60,70,80,90,100,120} × 512/256MB × 1/4/16T
- R1: ADAPTIVE 阈值重校准 (easy_ef {30,40,50}, easy_gap {1.004,1.006,1.008})
- R2: FLAT_VEC_MB {32-240} × 512/256MB × 1/4/16T
- R3: 最优组合验证 (旧参数 vs 新参数完整对比)
- R4: VL_POOL_THREADS {8-999} + CACHE_MB {32-128}

## 结论

### 256MB cgroup: 有显著调参空间

| 参数 | 200q 最优 | Sustained 最优 | 收益 |
|------|----------|--------------|------|
| REFINE_EF | 100 | **90** | +13.6% agg QPS |
| ADAPTIVE_EASY_EF | 50 | **40** | 额外 +12.7% agg QPS (配合 EF=90) |
| FLAT_VEC_MB | 64 | 64 (不变) | - |
| VL_POOL_THREADS | 14 | 14 (不变) | - |
| CACHE_MB | 64 | 64 (不变) | - |

组合效果（256MB 16T, ADAPTIVE, sustained）：
- 旧参数 (EF=100, eef=50): agg=2,892, steady=3,615, recall=95.54%
- 新参数 (EF=90, eef=40): agg=3,176 (+9.8%), steady=4,111 (+13.7%), recall=95.10%

### 512MB cgroup: 基本不变

| 参数 | 200q 最优 | Sustained 最优 | 收益 |
|------|----------|--------------|------|
| REFINE_EF | 100 | 100 (不变) | - |
| FLAT_VEC_MB | 160 | **64** (agg 最优) | +3-4% agg QPS |
| ADAPTIVE_EASY_EF | 50 | 50 (不变) | - |

512MB 下 FVC=64 提升 agg QPS 3-4%（SLA 口径），但 steady QPS 下降 12%。
推荐 SLA 场景用 FVC=64，长跑场景用 FVC=160。

### 不改的参数

- VL_POOL_THREADS=14: ±2-5% 噪声范围，当前值合理
- CACHE_MB=64: 两种 cgroup 下 agg QPS 最优
- GBDT_MARGIN=0.8: 已在 sustained 下调优 (R5 of gbdt-retrain)

### 重要发现

1. **200q 否决的参数在 sustained 下可能可行**：easy_ef=40 在 200q 下 recall=94.95% (< 95%)，
   sustained 下 recall=95.10% (≥ 95%)。因为 sustained recall 基线更高 (96.00% vs 95.75%)。

2. **512MB vs 256MB 最优参数不同**：512MB I/O 非瓶颈，参数不变；256MB I/O 是瓶颈，
   降 EF = 减 I/O = +QPS。cgroup 特化参数推荐是必要的。

3. **ADAPTIVE > GBDT 在参数变更时**：GBDT 模型在 EF=200 下训练，EF=90 下预测失准。
   ADAPTIVE 在线启发式对 EF 变化更鲁棒。

4. **FLAT_VEC_MB 的 agg/steady 权衡**：大 FVC 提升 steady（热缓存命中率）但伤害 agg
   （ramp-up 期吃 page cache 预算）。SLA 用 agg，推荐小 FVC。

## Source

> source: poc/sustained-param-retuning/ndf/TOPIC.md ; evidence/r0-r1-ef-adaptive-retuning-20260807.md ; r2-r3-fvc-combo-20260807.md ; r4-vlpool-cache-20260807.md
> track: promote ; Topic: sustained-param-retuning
