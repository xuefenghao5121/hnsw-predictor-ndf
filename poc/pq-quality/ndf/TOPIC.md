# TOPIC: pq-quality

> topic_id: pq-quality
> status: rejected (2026-08-04, DEC-072: M=32 是 SLA 达标唯一选择, OPQ 不可行)
> baseline_protocol: [[CON-SLA-014]] + DEEP10M 2GB cgroup；基线 530 QPS (1T, M=32)
> explore_surface: pq-codes
> baseline_trunk_sha: n/a
> baseline_status: n/a
> depends_on_topics: l4-cache-mgmt (promoted), refine-ef-tuning (并行)
> conflicts_with_topics: []
> binder: [[DEF-022]] / [[BEH-025]]

## Active hypothesis

改善 PQ 质量可减少 false positive，减少 fine rerank I/O 量。

## R0-R3 结果 (2026-08-03)

| PQ | dsub | EF | Recall | QPS | vs 基线 | note |
|----|------|-----|--------|-----|---------|------|
| M=32 | 3 | 300 | 95.05% | 530 | 基线 | 当前配置 |
| M=48 | 2 | 300 | 95.30% | 517 | -2% | codes太大, 无收益 |
| M=24 | 4 | 300 | 94.05% | 707 | +33% | **最佳单体** |
| M=24 | 4 | 200 | 92.40% | 963 | +82% | 联合EF=200 |

**M=24+EF=200 联合: 963 QPS (+82%), Recall=92.40%**

## Next gate

- [ ] 决策: M=24 (Recall 94%) 是否值得 promote
- [ ] 联合 refine-ef: M=24+EF=200 (Recall 92.4%) 是否可接受
- [x] 考虑 OPQ 旋转进一步改善 M=24 质量 -> **不可行**（OPQ 破坏图搜索）

## Verdict

**M=24 PQ 质量上限 94.05%（EF=300），无法达到 SLA 95%。OPQ 因破坏图搜索不可行。**

提升路径已穷尽（M=32 增大无收益，M=24 recall 不足，OPQ 破坏图搜索）。
建议：关闭 topic（边界已确认），如需提升 DEEP10M QPS 需放宽 SLA。

## Evidence

| date | round | PQ | EF | QPS | Recall | majfault | note |
|------|-------|----|-----|-----|--------|----------|------|
| 2026-08-03 | R0 | M=32 | 300 | 530 | 95.05% | 70145 | 基线 |
| 2026-08-03 | R1 | M=48 | 300 | 517 | 95.30% | 73809 | 无收益 |
| 2026-08-03 | R2 | M=24 | 300 | 707 | 94.05% | 70108 | +33% |
| 2026-08-03 | R3 | M=24 | 200 | 963 | 92.40% | 72603 | +82% 联合 |

## Commits

见 [COMMITS.md](COMMITS.md)
