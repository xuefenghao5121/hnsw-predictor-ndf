# Commit Ledger — perf-gap-4t

> [[DEF-023]] / [[BEH-025]]. Historical commits before binder adoption are not backfilled.
> New code/script commits MUST append a row + git trailers (`Topic:` / `Clauses:`).

| date | code_commit | ndf_commit | proposals | clauses | protocol | note |
|------|-------------|------------|-----------|---------|----------|------|
| 2026-08-05 | 1868dc2 | 973f7f5 | proposal-promote-perf-gap-4t.md | DEC-073, CON-SLA-016 | CON-SLA-014 | D1+D6 promoted. FVC default 4->64MB. 256MB cgroup SLA. All SLA pass. |
| 2026-08-06 | efe6ca8 | — | (docs/chore) | (see note) | (n/a) | historical; trailers absent; not rewritten |

> source: poc/perf-gap-4t/ndf/TOPIC.md ; proposals/proposal-promote-perf-gap-4t.md ; evidence/ ; COMMITS.md @ 1868dc2
> track: promote ; Topic: perf-gap-4t
