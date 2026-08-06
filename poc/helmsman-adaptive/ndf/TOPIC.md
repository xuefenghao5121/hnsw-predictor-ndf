# TOPIC: helmsman-adaptive

> topic_id: helmsman-adaptive
> status: promoted
> baseline_protocol: [[CON-SLA-014]] + [[CON-SLA-016]] + [[CON-SLA-017]]
> baseline_trunk_sha: 589e903
> baseline_status: current
> explore_surface: search-adaptive,fine-rerank
> depends_on_topics: (none)
> binder: [[DEF-022]]

## Active hypothesis

层次 A: PQ 距离间隙自适应 EF — 根据 PQ 粗筛 gap_ratio 动态调整 Phase B 候选数。
用户约束: recall ≥ 95% 即可。

## 基线 (Trunk 589e903)

| 配置 | QPS | Recall |
|------|-----|--------|
| SIFT1M 256MB 1T | 2,623 | 95.80% |
| SIFT1M 256MB 4T | 8,356 | 95.80% |
| SIFT1M 256MB 8T | 14,703 | 95.80% |
| SIFT1M 256MB 16T | 18,344 | 95.75% |

## 最优配置

```
ADAPTIVE_EF=1
ADAPTIVE_EASY_GAP=1.006   # gap ≥ 此值的 query 判为 "容易"
ADAPTIVE_HARD_GAP=1.002   # gap ≤ 此值的 query 判为 "困难"
ADAPTIVE_EASY_EF=50       # 容易 query 的 Phase B 候选上限
ADAPTIVE_HARD_EF=200      # 困难 query 的 Phase B 候选上限
```

## R0: PQ gap 分布 ✅

| P10 | P25 | P50 | P75 | P90 | Max |
|-----|-----|-----|-----|-----|-----|
| 1.001 | 1.003 | 1.006 | 1.013 | 1.022 | 1.045 |

## R1d: 阈值调优 ✅

recall ≥ 95% 约束下的最优甜点: easy_gap=1.006, easy_ef=50

## R2: 最终 scaling 验证 ✅

| 线程 | Recall | Adaptive QPS | Baseline QPS | Δ |
|------|--------|-------------|-------------|---|
| 256MB 1T | 95.30% | 2,669 | 2,623 | +1.8% |
| 256MB 4T | 95.30% | 10,971 | 8,356 | **+31.3%** ✅ |
| 256MB 8T | 95.30% | 19,397 | 14,703 | **+31.9%** ✅ |
| 256MB 16T | 95.30% | 19,550 | 18,344 | +6.6% |

## R3: 512MB 回归 ✅ (之前数据)

512MB 下持平/略退 (-0.4 ~ -7.3%)。opt-in 默认关闭，可接受。

## Promote 条件评估

✅ recall ≥ 95% (全部配置 95.30%)
✅ 256MB 4T/8T 巨大收益 (+31%)
✅ 环境变量 opt-in (ADAPTIVE_EF 默认关闭)
✅ 不改 Trunk 默认行为
⚠️ 512MB 略退 → 默认关闭可接受
⚠️ SIFT1M only (DEEP10M 待验证)

## 层次 B (Fine Rerank 早终止): REJECTED

### R4: 层次 B 单独验证

| ET 阈值 | Recall | QPS |
|---------|--------|-----|
| 5  | 87.60% | 7,076 |
| 10 | 91.10% | 5,951 |
| 15 | 92.15% | 7,842 |
| 20 | 92.60% | 7,370 |
| 30 | 93.35% | 7,733 |

**全部 recall < 95%**，且 QPS 无收益。

### R5: 层次 A+B 组合

| ET 阈值 | Recall | QPS | vs A-only QPS |
|---------|--------|-----|---------------|
| 10 | 91.00% | 7,194 | worse |
| 15 | 92.35% | 8,293 | worse |
| 20 | 92.80% | 8,785 | worse |
| 30 | 93.85% | 7,782 | worse |
| 50 | 94.60% | 10,210 | -6.9% |

**A+B 叠加全面不如 A 单独。**

### 根因分析

1. pread 路径先批量读全部页 → 早终止只能省距离计算 (L2 ~几十 ns), 不能省 I/O
2. SIFT1M 候选距离无明显拐点 → 连续无改善阈值难设定
3. 层次 A 已减少候选 → B 在已缩减集合上更难触发, 反而引入额外分支开销
4. 如改增量 pread (逐候选读), syscall 暴增, 预期也不乐观

### 结论: 层次 B 在当前 pread 架构下不成立, reject

DEC 条款: [[DEC-081]] (draft) — Fine Rerank 早终止在批量 pread 架构下无效

## Next gate

- [x] R0: gap 分布 ✅
- [x] R1d: 阈值调优 ✅
- [x] R2: scaling 验证 ✅
- [x] R3: 512MB 回归 ✅
- [x] R4: 层次 B 单独验证 → **rejected** ❌
- [x] R5: A+B 组合验证 → **不如 A 单独** ❌
- [ ] 决策: 层次 A promote (opt-in), 层次 B reject

## Draft clauses

| ID | In spec/? | Notes |
|----|-----------|-------|
| BEH-033 (draft) | no | PQ 距离间隙自适应 EF (opt-in) |
| API-017 (draft) | no | ADAPTIVE_EF + 阈值环境变量 |
| DEC-080 (draft) | no | SIFT1M gap 校准 + recall/QPS 权衡 |

## Evidence

| ID | Description |
|----|-------------|
| R0-gap | 200q gap 分布 (P10=1.001 P50=1.006 P90=1.022) |
| R1d-sweep | 阈值调优 (8 配置) |
| R2-final | 256MB 1-16T 最终配置 (recall 95.30%) |

## Commits

见 [COMMITS.md](COMMITS.md)
