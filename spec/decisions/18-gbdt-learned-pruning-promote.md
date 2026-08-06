# DEC-082: GBDT vs 启发式效果对比 + I/O bound 场景分析

> topic: gbdt-learned-pruning
> status: accepted
> date: 2026-08-06
> Promotes: gbdt-learned-pruning

## 背景

helmsman-adaptive (BEH-033) 用单一 gap_ratio 启发式，200q 实测 +31% QPS。
本 DEC 记录 GBDT 多特征预测的对比结果和适用场景边界。

## 决策

### 1. GBDT 在 I/O bound 场景下显著优于启发式

| NQ | Adaptive vs Base | GBDT vs Base |
|----|-----------------|--------------|
| 200 | +5.6% | +3.1% |
| 1,000 | +35.7% | +71.7% |
| 10,000 | +37.4% | +89.4% |

### 2. 根因

GBDT 用 11 维特征精准预测 per-query 最小候选数（avg N=52 vs 固定 100, -48% I/O）。
启发式只有 3 档分类（easy/normal/hard），平均 N=88（-12% I/O）。

### 3. 共存策略

- ADAPTIVE_EF (BEH-033): 简单，无模型依赖，适合 cache-warm 场景
- LEARNED_EF (BEH-034): 精准，需 SIFT1M 训练模型，适合 I/O bound 场景
- 两者 opt-in 默认关闭，互斥但可共存于代码中

## 证据

- 10K query 256MB 4T: GBDT 4,418 vs Adaptive 3,204 vs Baseline 2,332
- POC: `poc/gbdt-learned-pruning/ndf/TOPIC.md`
