# COMMITS — hotspot-optimization

Ledger skeleton ([[DEF-023]]). Append when this topic's code or measure scripts land.

| date | code_commit | ndf_commit | proposals | clauses | protocol | note |
|------|-------------|------------|-----------|---------|----------|------|
| 2026-08-20 | 4f7a4b5adc1aabb4c4e48ef77af774b168cb1e16 | 4f7a4b5adc1aabb4c4e48ef77af774b168cb1e16 | spec/open/proposal-poc-hotspot-optimization.md | META-007 META-011 BEH-018 | none (baseline copy only) | `poc-prepare-baseline`: Trunk对照拷贝入 `src/`（disk_hnsw + simd*）；无 D1 改动、无 Numbers |
| 2026-08-18 | — (withdrawn) | — | spec/open/proposal-poc-hotspot-optimization.md | CHR-006 (recall unchanged) | none (no valid Numbers) | D1 AVX2 gather **WITHDRAWN** — Cursor self-execute, unbound writes; code ledger empty (src/ Makefile build/ removed). equiv 20000/20000 NOT treated as Numbers |
| 2026-08-22 | e37ab5e23a47dfb8a1d6167021d688d0dcd00d36 (measured) | e37ab5e23a47dfb8a1d6167021d688d0dcd00d36 | spec/open/proposal-poc-hotspot-optimization.md | CON-SLA-014 CON-SLA-019 CON-SLA-020 META-007 | CON-SLA-020 sustained | D1 measured under ACP lease ep-c82a69ac: agg QPS=2280.5 (baseline 2221.4, +2.66%) steady(R15)=2733.9 recall@10=96.59% (unchanged) RSS=332MB; evidence ndf/evidence/poc_measurement-*.md |
| 2026-08-22 | 948f789709e5397275f29696b867491646470753 (lease base) | 948f789709e5397275f29696b867491646470753 | spec/open/proposal-poc-hotspot-optimization.md | META-011 BEH-018 BEH-025 CHR-006 (recall unchanged) | none (no Numbers yet) | D1 SIMD pqAdcDistance gather (AVX2 `_mm256_i32gather_ps`, 8-lane) landed in poc src: simd_{x86,arm,scalar}.h ADD pqAdcDistance only (Trunk headers still provide pqBuildTable_dsub4/SIMD_PREFETCH); disk_hnsw.cpp pqDistance fast path calls pqAdcDistance. compile OK, M=32 bit-identical vs scalar; Numbers pending (separate poc_measurement) |

## 说明

- 2026-08-20 `poc-prepare-baseline` 恢复正式对照工作区；见 `src/BASELINE_COPY.md`。
- 2026-08-18 的 D1 实现由 Cursor 在未经正式委派下自我执行，属未绑定写入，
  已全部撤回（`src/`、`Makefile`、`build/`、`ndf/evidence/d1-pq-gather-equiv-20260818.md`）。
- 该次 kernel 等价性结果（20000/20000 bitwise）**不作为 Numbers / DELTA 证据**。
- D1 实现仍须人工 `selected_decision=implement` 后经 Claude Code 委派，再按 [[DEF-023]] 追加正式实现行。
