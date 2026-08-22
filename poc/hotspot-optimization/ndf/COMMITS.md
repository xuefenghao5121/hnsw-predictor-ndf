# COMMITS — hotspot-optimization

Ledger skeleton ([[DEF-023]]). Append when this topic's code or measure scripts land.

| date | code_commit | ndf_commit | proposals | clauses | protocol | note |
|------|-------------|------------|-----------|---------|----------|------|
| 2026-08-20 | 4f7a4b5adc1aabb4c4e48ef77af774b168cb1e16 | 4f7a4b5adc1aabb4c4e48ef77af774b168cb1e16 | spec/open/proposal-poc-hotspot-optimization.md | META-007 META-011 BEH-018 | none (baseline copy only) | `poc-prepare-baseline`: Trunk对照拷贝入 `src/`（disk_hnsw + simd*）；无 D1 改动、无 Numbers |
| 2026-08-18 | — (withdrawn) | — | spec/open/proposal-poc-hotspot-optimization.md | CHR-006 (recall unchanged) | none (no valid Numbers) | D1 AVX2 gather **WITHDRAWN** — Cursor self-execute, unbound writes; code ledger empty (src/ Makefile build/ removed). equiv 20000/20000 NOT treated as Numbers |

## 说明

- 2026-08-20 `poc-prepare-baseline` 恢复正式对照工作区；见 `src/BASELINE_COPY.md`。
- 2026-08-18 的 D1 实现由 Cursor 在未经正式委派下自我执行，属未绑定写入，
  已全部撤回（`src/`、`Makefile`、`build/`、`ndf/evidence/d1-pq-gather-equiv-20260818.md`）。
- 该次 kernel 等价性结果（20000/20000 bitwise）**不作为 Numbers / DELTA 证据**。
- D1 实现仍须人工 `selected_decision=implement` 后经 Claude Code 委派，再按 [[DEF-023]] 追加正式实现行。
