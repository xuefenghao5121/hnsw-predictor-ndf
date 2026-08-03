# TOPIC: l4-cache-mgmt

> topic_id: l4-cache-mgmt
> status: exploring
> baseline_protocol: [[CON-SLA-014]] + SIFT1M 512MB cgroup；Buffered 1T 对齐基线 22.9 QPS ([[DEC-066]])
> depends_on_topics: (none; **this topic precedes** io-pipelining re-bench)
> binder: [[DEF-022]] / [[BEH-025]]

## Active hypothesis

严格隔离下 peak file 顶满导致内核盲目 LRU；对 vecblocks 做精准 DONTNEED / WILLNEED /
基于 `FINE_FADVISE` 的选择性驱逐，可抬升 Buffered QPS（aspirational ≥×1.5）。

## Next gate

- [ ] 提案确认后委派 `poc/l4-cache-mgmt/` 实现 R0 复跑
- [ ] R1 机制 A（L4_DONTNEED）

## Draft clauses

| ID | In spec/? | Notes |
|----|-----------|-------|
| [[BEH-024]] | yes (`status=draft`) | L4 主动管理；禁 EVICT 幽灵 |

## Proposals

| Role | Path | Status |
|------|------|--------|
| root | [proposals/proposal-l4-cache-mgmt.md](proposals/proposal-l4-cache-mgmt.md) → `spec/open/proposal-l4-cache-mgmt.md` | Pending |

## Evidence

见 [evidence/](evidence/)（有报告时放入）；严格隔离基线见 `spec/open/validation-20260803-strict-baseline.md`。
