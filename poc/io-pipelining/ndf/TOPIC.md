# TOPIC: io-pipelining

> topic_id: io-pipelining
> status: exploring
> baseline_protocol: [[CON-SLA-014]] + [[DEC-066]] 观测基线；旧 DEC-063/064 pipe 结论搁置至 C 组重测
> depends_on_topics: l4-cache-mgmt（**优先稳住 L4 后再叠 L5**，见 l4 提案）
> binder: [[DEF-022]] / [[BEH-025]]

## Active hypothesis

在严格隔离与真实 I/O/热集溢出场景下，`pipe_ring_`（[[BEH-021]]）可相对 R0 带来可测收益；
白嫖 / EVICT 幽灵口径下的旧结论不可作 promote 依据。

## Next gate

- [ ] 等待 / 并行：l4-cache-mgmt 进展或独立 C 组 R0 画像
- [ ] 按 `proposal-io-behavior-correction` r2 重测 R0 vs R1

## Draft clauses

| ID | In spec/? | Notes |
|----|-----------|-------|
| [[BEH-021]] | yes (draft) | pipe_ring_ L5 |
| [[BEH-022]] | yes (draft) | L1 prefetch |
| [[BEH-023]] | yes (draft) | PIPE_L4 readahead fill |
| [[API-010]] | yes (draft) | PIPE_* env |
| [[CON-SLA-013]] | yes (draft) | POC SLA targets |

## Proposals

| Role | Path | Status |
|------|------|--------|
| root | [proposals/proposal-io-pipelining.md](proposals/proposal-io-pipelining.md) | see open/ |
| amend | [proposals/proposal-io-behavior-correction.md](proposals/proposal-io-behavior-correction.md) | Pending r2 |

## Evidence

见 [evidence/](evidence/)；历史 NOTES：`../NOTES.md`。
