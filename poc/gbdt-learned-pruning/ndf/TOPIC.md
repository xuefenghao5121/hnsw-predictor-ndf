# TOPIC: gbdt-learned-pruning

> topic_id: gbdt-learned-pruning
> status: promoted
> baseline_protocol: [[CON-SLA-014]] + [[CON-SLA-016]]
> baseline_trunk_sha: 7f59fae
> baseline_status: stale (200q cache-hit 假象已证实)
> explore_surface: search-adaptive,learned-pruning,fine-rerank
> depends_on_topics: helmsman-adaptive (promoted)
> binder: [[DEF-022]]

## Active hypothesis

GBDT 模型利用多特征预测 per-query 候选数，在 I/O bound 场景下获得显著 QPS 提升。
recall ≥ 95%。

**结论: 假设成立。** I/O bound 场景下 GBDT +33~124% QPS。

## ★ 关键发现: 200q cache-hit 假象

200 query 的 working set (~10MB) 全进 page cache → I/O ≈ 0 → 测的是内存搜索性能。
10K query 的 working set (~488MB) 远超 cgroup → 真实 I/O bound 性能。

详见 [sla-reevaluation.md](sla-reevaluation.md)

| NQ | Baseline QPS | 备注 |
|----|-------------|------|
| 200 | 8,856 | cache-hit 假象 |
| 1,000 | 4,095 | 部分超 cache |
| 10,000 | 2,332 | 真实 I/O bound |

## 最优配置

```
LEARNED_EF=1
GBDT_MARGIN=0.8
```

## R0: Profiling ✅

10K query, ef=200. P50 min_n=21, 68% query 只需 ≤30 候选。

## R1: LightGBM 训练 ✅

100 棵树, depth=4, MAE=46.3, 导出 186KB C++ if-else.

## R4: margin 调优 ✅

margin=0.8 最优。

## 三方对比 (256MB 4T, 随 NQ 变化)

| NQ | Baseline | Adaptive | GBDT | GBDT vs Base |
|----|----------|----------|------|-------------|
| 200 | 8,856 | 9,349 | 9,127 | +3.1% |
| 1,000 | 4,095 | 5,555 | 7,032 | +71.7% |
| 10,000 | 2,332 | 3,204 | 4,418 | +89.4% |

GBDT 价值随 NQ 增大而放大 (I/O 越是瓶颈，减少候选越有效)。

## R5: 完整 scaling (10K query) ✅

256MB:
| 线程 | Baseline | GBDT | Δ |
|------|---------|------|---|
| 1T | 1,121 | 1,555 | +38.7% |
| 4T | 2,341 | 4,418 | +88.7% |
| 8T | 2,314 | 4,919 | +112.6% |
| 16T | 2,099 | 4,707 | +124.3% |

512MB:
| 线程 | Baseline | GBDT | Δ |
|------|---------|------|---|
| 1T | 1,428 | 1,903 | +33.2% |
| 4T | 4,129 | 6,324 | +53.2% |
| 8T | 5,199 | 9,433 | +81.4% |
| 16T | 5,583 | 11,149 | +99.7% |

hnswlib unlimited (739MB) 10K 参考:
| 线程 | QPS |
|------|-----|
| 1T | 6,395 |
| 4T | 22,808 |
| 8T | 35,515 |
| 16T | 41,839 |

## Promote 条件评估

✅ recall ≥ 95% (10K: 97.33%, 200q: 95.75%)
✅ I/O bound 场景 QPS +33~124%
✅ 512MB 也有收益 (+33~100%)
✅ 模型导出 C++ (186KB, 无运行时 Python 依赖)
✅ opt-in (LEARNED_EF 默认关闭)
✅ 泛化性: 200q/1Kq/10Kq 全部有收益
⚠️ 200q 下不如 Adaptive (cache-hit 场景 GBDT 多特征无优势)
⚠️ 需要 DEEP10M 验证跨数据集泛化

## Next gate

- [x] R0-R5 全部完成
- [ ] 决策: promote (opt-in)

## Draft clauses

| ID (draft) | 说明 |
|------------|------|
| BEH-034 (draft) | GBDT 学习式候选数预测 |
| API-018 (draft) | LEARNED_EF, GBDT_MARGIN 环境变量 |
| DEC-082 (draft) | GBDT vs 启发式效果对比 |
| DEC-083 (draft) | 200q cache-hit 假象发现 + SLA 修正建议 |

## Commits

见 [COMMITS.md](COMMITS.md)
