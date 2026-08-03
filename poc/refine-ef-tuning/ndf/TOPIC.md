# TOPIC: refine-ef-tuning

> topic_id: refine-ef-tuning
> status: exploring
> baseline_protocol: [[CON-SLA-014]] + DEEP10M 2GB cgroup；基线 685 QPS (1T, flat_vec=128MB)
> depends_on_topics: l4-cache-mgmt (promoted), pq-quality (并行)
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

- [ ] 决策: 是否放宽 SLA 到 94%
- [ ] 与 pq-quality 联合: 更好 PQ -> 更低 REFINE_EF -> 更高 QPS

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
