# Commit Ledger — multi-thread-scaling

> [[DEF-023]] / [[BEH-025]]. Historical commits before binder adoption are not backfilled.
> New code/script commits MUST append a row + git trailers (`Topic:` / `Clauses:`).

| date | code_commit | ndf_commit | proposals | clauses | protocol | note |
|------|-------------|------------|-----------|---------|----------|------|
| 2026-08-05 | 3258ce0 | 3258ce0 | proposal-multi-thread-scaling.md | none | CON-SLA-014 | POC topic created; SIFT1M scaling sweep; FineRerank race fix |
| 2026-08-05 | 1531316 | 1531316 | proposal-multi-thread-scaling.md | none | CON-SLA-014 | DEEP10M scaling sweep; 4T peak, 8T+ regression |
| 2026-08-05 | b43db9a | b43db9a | proposal-multi-thread-scaling.md | none | drop_caches (no cgroup) | v2: hnswlib unlimited memory baseline |
| 2026-08-05 | 1d14de7 | 1d14de7 | proposal-promote-finererank-threadsafe.md | BEH-001,BEH-007,BEH-002 | CON-SLA-014 | Promoted: FineRerank race fix + MT benchmark -> Trunk src/ |
| 2026-08-05 | 62b0c9c | — | (Dir B) | (see note) | CON-SLA-014 | historical; trailers absent; not rewritten |
| 2026-08-05 | 5b03634 | — | (Dir C) | (see note) | CON-SLA-014 | historical; trailers absent; not rewritten |
| 2026-08-05 | 9bfe551 | — | (Dir A) | (see note) | CON-SLA-014 | historical; trailers absent; not rewritten |
| 2026-08-05 | e5a1155 | — | (C2/A3) | (see note) | CON-SLA-014 | historical; trailers absent; not rewritten |
| 2026-08-05 | 750f9bd | — | (A2) | (see note) | CON-SLA-014 | historical; trailers absent; not rewritten |
| 2026-08-05 | da2d8cb | — | (sweep) | (see note) | CON-SLA-014 | historical; trailers absent; not rewritten |
| 2026-08-05 | — | efa919b | proposal-promote-mt-scaling.md | BEH-027, API-013, CON-SLA-017, DEC-074 | CON-SLA-014 | A2+C2 promoted. Peak 30332 QPS (16T). |
| 2026-08-06 | efe6ca8 | — | (docs/chore) | (see note) | (n/a) | historical; trailers absent; not rewritten |

> source: poc/multi-thread-scaling/ndf/TOPIC.md ; evidence/a2-lockless-bg-20260805.md ; comprehensive-sweep-20260805.md
> track: promote ; Topic: multi-thread-scaling
