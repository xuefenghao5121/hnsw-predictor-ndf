# Commit Ledger: cluster-gbdt

> topic_id: cluster-gbdt
> schema: BEH-025 / DEF-023
> status: exploring

| date | code_commit | ndf_commit | proposals | clauses | protocol | note |
|------|-------------|------------|-----------|---------|----------|------|
| 2026-08-10 | `a9c76de` | `a9c76de` | N/A | BEH-034, BEH-037 | CON-SLA-020 sustained | R0 cluster-purity GBDT; historical negative result |

Future code or measurement commits MUST append a row with the current baseline and evidence
binding. Documentation-only gate/binder reconciliation does not invent a code commit.

| 2026-08-13 | N/A (doc-only) | N/A | N/A | N/A | N/A | Binder pipeline audit: all 6 facets rechecked, no amendment needed; test.numbers_pending is topic-health finding, not binder gap |
| 2026-08-13 | `a143392` (remeasure) | `a143392` | N/A | BEH-034, BEH-037 | CON-SLA-020 sustained | R0 baseline remeasured: 512MB agg=2160 steady=2467 recall=96.59%; 256MB agg=1870 steady=2029 recall=96.60% |
| 2026-08-13 | N/A | N/A | N/A | BEH-034, BEH-037 | CON-SLA-020 sustained | Audit correction: preceding `a143392` row is unverified (repo HEAD, not a POC measurement commit); no run/lease/completion/evidence receipt found. MUST NOT restore baseline current. |
| 2026-08-14 | `a143392` (measured) | worktree dirty | N/A | BEH-025, BEH-037, CON-SLA-020 | CON-SLA-020 sustained | Verified R0 remeasure under ACP lease `run-repair-poc-measurement-cluster-gbdt-20260814T083515Z`; evidence `ndf/evidence/r0-remeasure-verified-20260814.md` |
| 2026-08-14 | N/A (analysis only) | `a143392` | N/A | BEH-025, BEH-034, BEH-037 | CON-SLA-020 sustained | R1 entropy analysis (A1): entropy saturated 0.9945, purity 6.3%, top-100 spans ~94/1024 clusters → no incremental signal; evidence `ndf/evidence/r1-entropy-analysis-20260814.md` |
