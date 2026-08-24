# TOPIC: io-pipelining

> topic_id: io-pipelining
> status: rejected (2026-08-04, DEC-071: WILLNEED 取代 pipe_ring_)
> baseline_protocol: [[CON-SLA-014]] + [[DEC-066]] 观测基线；旧 DEC-063/064 pipe 结论搁置至 C 组重测
> explore_surface: fine-rerank,io-pipe
> baseline_trunk_sha: n/a
> baseline_status: n/a
> depends_on_topics: l4-cache-mgmt（**优先稳住 L4 后再叠 L5**，见 l4 提案）
> conflicts_with_topics: []
> binder: [[DEF-022]] / [[BEH-025]]

## Active hypothesis

在严格隔离与真实 I/O/热集溢出场景下，`pipe_ring_`（[[BEH-021]]）可相对 R0 带来可测收益；
白嫖 / EVICT 幽灵口径下的旧结论不可作 promote 依据。

## Next gate

- [x] 按 `proposal-io-behavior-correction` r2 重测 R0 vs R1
- [x] DEEP10M 2GB: R1 vs R0 = -0.9%（pipe 无收益）
- [x] DEEP10M 3GB: R1 vs R0 = -1.8%（pipe 开销）
- [ ] 决策：负结果闭环（[[BEH-020]]）或继续探索

## Verdict

**pipe_ring_ 在 CON-SLA-014 下无收益。WILLNEED (DEC-070) 已实现 I/O 并行，使 pipe 失去独立价值。**

pipe_hits=255 证明机械工作正常，但 WILLNEED 的内核 readahead 已在 pread 前启动异步预取，
pipe_ring_ 的预取与 WILLNEED 完全重叠。建议按 [[BEH-020]] 负结果闭环。

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
