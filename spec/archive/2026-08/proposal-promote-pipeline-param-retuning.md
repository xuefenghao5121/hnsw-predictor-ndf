> track: promote
> topic: pipeline-param-retuning
> status: proposal
> 日期: 2026-08-08

# 提案: Promote pipeline-param-retuning - 256MB 参数调优结论

## 引用

- TOPIC: `poc/pipeline-param-retuning/ndf/TOPIC.md`
- Evidence: `poc/pipeline-param-retuning/ndf/evidence/r0-r4-redo-20260808.md`
- 基线: CON-SLA-020 (sustained 金标), 基线对齐 +0.5% ✅

## 晋升内容

本 promote 不改 Trunk `src/` 代码（pipeline 默认 M=16 已正确），仅修改推荐参数注释 + 新增 DEC。

### Amend: API-011 (Benchmark / 调参环境变量)

追加 256MB sustained BASE 模式推荐：
- `REFINE_EF`: 256MB sustained BASE 推荐 65 (recall 95.52%, +127% QPS vs EF=100)
- 与现有 DEC-086 推荐 (ADAPTIVE EF=90) 并列

### Amend: API-017 (PQ 距离间隙自适应 EF)

追加说明：
- ADAPTIVE 在 M=16 EF=65 下增益有限 (+3-7%)，因 recall 余量仅 0.52pp
- ADAPTIVE 在 M=24 EF=60 下增益显著 (+68%)，推荐 eef=40

### New: DEC-087 (pipeline-param-retuning 结论)

记录：
1. M=16 EF=65 是 256MB BASE 模式 Pareto 最优 (agg=2,483, recall=95.52%)
2. M=24 EF=60 + ADAPTIVE 是 256MB ADAPTIVE 模式最优 (agg=2,530, recall=96.22%)
3. M=16 EF=65 + ADAPTIVE 16T 最高吞吐 (agg=4,057, recall=95.17%)
4. Block size 32K vs 64K: +52.5% QPS (延期 - 需 pipeline 重建验证)
5. GBDT-v3 重训: 负结果 (256MB 低 EF 下无效)
6. PQ M=32 仍是唯一达标选择

### 不改的条款

- CON-SLA-020: SLA 阈值数字不变 (基线仍有效)
- CON-SLA-016/017/018: cache-warmed 护栏不变
- Trunk `src/` 默认值: REFINE_EF=200, FLAT_VEC_MB=64 不变

## 语义核决策 ([[META-004]] / [[BEH-019]] §6)

- **不要**: 本 promote 仅参数推荐注释，无新行为契约。L1 API 条款 + DEC 足够。
  无需蒸馏 `spec/models/` 语义核。

## 基线 stale ([[BEH-025]] / [[BEH-019]])

本 promote 不改 Trunk `src/` 代码，无 exploring 主题受影响。
pipeline-param-retuning TOPIC 标 `promoted`。

## 表面冲突 ([[BEH-018]] §9)

explore_surface: graph-structure, pq-encoding, block-layout
无活跃 exploring 主题相交。已 promoted 主题 (sustained-param-retuning, gbdt-retrain) 为依赖关系，不冲突。

## trunk-ref

本 promote 不改代码，trunk-ref 不需要更新。
API-011/API-017 的 trunk-ref 保持 c63694f (上一个 promote SHA)。

## 证据摘要

| Config | 1T Agg QPS | 16T Agg QPS | Recall | 来源 |
|--------|-----------|------------|--------|------|
| M=16 EF=65 BASE | 2,483 | 3,170 | 95.52% | R5.1 |
| M=16 EF=65 +ADAPTIVE | 2,554 | 4,057 | 95.17% | R5.2 |
| M=24 EF=60 +ADAPTIVE | 2,530 | - | 96.22% | R1' |
| M=16 EF=100 (旧默认) | 1,092 | - | 97.76% | R0' |
| Block 32K vs 64K | +52.5% | - | 同 | R4' (延期) |
| GBDT-v3 | ≈BASE | - | 同 | R6 (负结果) |

> source: poc/pipeline-param-retuning/ndf/TOPIC.md ; evidence/r0-r4-redo-20260808.md
> track: promote ; Topic: pipeline-param-retuning
