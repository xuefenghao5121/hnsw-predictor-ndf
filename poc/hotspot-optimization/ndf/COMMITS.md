# COMMITS — hotspot-optimization

Ledger skeleton ([[DEF-023]]). Append when this topic's code or measure scripts land.

| date | code_commit | ndf_commit | proposals | clauses | protocol | note |
|------|-------------|------------|-----------|---------|----------|------|
| 2026-08-18 | — (withdrawn) | — | spec/open/proposal-poc-hotspot-optimization.md | CHR-006 (recall unchanged) | none (no valid Numbers) | D1 AVX2 gather **WITHDRAWN** — Cursor self-execute, unbound writes; code ledger empty (src/ Makefile build/ removed). equiv 20000/20000 NOT treated as Numbers |
| 2026-08-19 | (pending this commit) | (pending this commit) | spec/open/proposal-poc-hotspot-optimization.md | META-007, BEH-018, CON-POC-001 | CON-SLA-020 / cfg-m24-ef60 (identity only; Numbers still pending) | poc_prepare_baseline: byte-identical Trunk copies into `src/` + Makefile/`run_r0.sh`. No D1 edit. No Numbers. |

## 说明

- 2026-08-18 的 D1 实现由 Cursor 在未经正式委派下自我执行，属未绑定写入，
  已全部撤回（`src/`、`Makefile`、`build/`、`ndf/evidence/d1-pq-gather-equiv-20260818.md`）。
- 该次 kernel 等价性结果（20000/20000 bitwise）**不作为 Numbers / DELTA 证据**。
- 2026-08-19 的 `poc_prepare_baseline` 只恢复 **未改动** 的 Trunk 对照切片，形成可 R0
  测量的工作区；不是 D1 实现，也不是测量 hop。`code_commit` / `ndf_commit` 在本行落地
  commit SHA 写入后回填。
