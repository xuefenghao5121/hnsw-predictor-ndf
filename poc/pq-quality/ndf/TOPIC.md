# TOPIC: pq-quality

> topic_id: pq-quality
> status: exploring
> baseline_protocol: [[CON-SLA-014]] + DEEP10M 2GB cgroup；基线 580 QPS (1T)
> depends_on_topics: l4-cache-mgmt (promoted)
> binder: [[DEF-022]] / [[BEH-025]]

## Active hypothesis

改善 PQ 质量（增大 M / 调 dsub / OPQ）可减少 false positive 候选，减少 fine rerank I/O 量。

## Next gate

- [ ] R0: 当前 PQ (M=32, dsub=3) 基线确认
- [ ] R1-R2: M=48/64 扫描（需 retrain PQ codes）
- [ ] 监控: recall, QPS, majfault, 候选数

## Proposals

| Role | Path | Status |
|------|------|--------|
| root | `spec/open/proposal-pq-quality.md` | Draft |

## Evidence

(待测试)

## Commits

见 [COMMITS.md](COMMITS.md)
