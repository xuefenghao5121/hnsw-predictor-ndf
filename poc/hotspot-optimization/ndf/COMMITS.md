# COMMITS — hotspot-optimization

Ledger skeleton ([[DEF-023]]). Append when this topic's code or measure scripts land.

| date | code_commit | ndf_commit | proposals | clauses | protocol | note |
|------|-------------|------------|-----------|---------|----------|------|
| 2026-08-18 | — (withdrawn) | — | spec/open/proposal-poc-hotspot-optimization.md | CHR-006 (recall unchanged) | none (no valid Numbers) | D1 AVX2 gather **WITHDRAWN** — Cursor self-execute, unbound writes; code ledger empty (src/ Makefile build/ removed). equiv 20000/20000 NOT treated as Numbers |

## 说明

- 2026-08-18 的 D1 实现由 Cursor 在未经「可以开始实现」委派下自我执行，属未绑定写入，
  已全部撤回（`src/`、`Makefile`、`build/`、`ndf/evidence/d1-pq-gather-equiv-20260818.md`）。
- 该次 kernel 等价性结果（20000/20000 bitwise）**不作为 Numbers / DELTA 证据**。
- 代码 ledger 当前为空：无正式 code_commit。待人工 `selected_decision=implement` 后，
  经 Claude Code 委派重新实现，再按 [[DEF-023]] 追加正式行。
