# TOPIC: refine-ef-tuning

> topic_id: refine-ef-tuning
> status: rejected (2026-08-04, DEC-072: Recall≥95% 约束下 EF=300 是硬约束)
> baseline_protocol: [[CON-SLA-014]] + DEEP10M 2GB cgroup；基线 685 QPS (1T, flat_vec=128MB)
> explore_surface: refine-ef
> baseline_trunk_sha: n/a
> baseline_status: n/a
> depends_on_topics: l4-cache-mgmt (promoted), pq-quality (并行)
> conflicts_with_topics: []
> binder: [[DEF-022]] / [[BEH-025]]

## Active hypothesis

降 REFINE_EF 可线性减少 fine rerank I/O 量，在 recall 仍可接受时最大化 QPS。

## R0-R4 结果 (2026-08-03)

| REFINE_EF | Recall | QPS | vs R0 | majfault |
|-----------|--------|-----|-------|----------|
| 300 | 95.05% | 685 | 基线 | 69075 |
| 200 | 94.25% | 865 | +26% | 72791 |
| 150 | 93.00% | 1077 | +57% | 72948 |
| 100 | 90.85% | 1315 | +92% | 72988 |
| 50 | 83.20% | 1709 | +149% | 73584 |

**最佳平衡点: REFINE_EF=200, Recall=94.25%, QPS=865 (+26%)**

## Next gate

- [x] R0-R4: pre-WILLNEED 扫描（EF=300/200/150/100/50）
- [x] R5: WILLNEED 下 REFINE_EF 重扫 + PQ 联合
- [x] 决策：Recall≥95% 约束下 EF=300 是硬约束，无优化空间

## Verdict

**Recall≥95% 约束下已到天花板。** EF=300+M=32 是唯一达标组合（567 QPS）。
M=24 PQ 质量上限 94.05%（不足以达标）。
EF=250 差 0.2pp（94.85%），除非放宽 SLA。

建议：关闭 topic 或等 100M 规模重评。

## Evidence

| date | round | REFINE_EF | QPS | Recall | majfault | note |
|------|-------|-----------|-----|--------|----------|------|
| 2026-08-03 | R0 | 300 | 685 | 95.05% | 69075 | 基线 |
| 2026-08-03 | R1 | 200 | 865 | 94.25% | 72791 | +26%, -0.8pp |
| 2026-08-03 | R2 | 150 | 1077 | 93.00% | 72948 | +57%, -2pp |
| 2026-08-03 | R3 | 100 | 1315 | 90.85% | 72988 | +92%, -4pp |
| 2026-08-03 | R4 | 50 | 1709 | 83.20% | 73584 | +149%, -12pp |

## Commits

见 [COMMITS.md](COMMITS.md)
