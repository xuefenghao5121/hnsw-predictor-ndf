# TOPIC: refine-ef-tuning

> topic_id: refine-ef-tuning
> status: exploring
> baseline_protocol: [[CON-SLA-014]] + DEEP10M 2GB cgroup；基线 580 QPS (1T)
> depends_on_topics: l4-cache-mgmt (promoted, flat_vec cap fix 已合入)
> binder: [[DEF-022]] / [[BEH-025]]

## Active hypothesis

降 REFINE_EF 可线性减少 fine rerank I/O 量，在 recall 仍可接受时最大化 QPS。

## Next gate

- [ ] R0-R4: DEEP10M 2GB, REFINE_EF=300/200/150/100/50 扫描
- [ ] 找到 recall ≥ 95% 的最低 REFINE_EF

## Proposals

| Role | Path | Status |
|------|------|--------|
| root | `spec/open/proposal-refine-ef.md` | Draft |

## Evidence

(待测试)

## Commits

见 [COMMITS.md](COMMITS.md)
