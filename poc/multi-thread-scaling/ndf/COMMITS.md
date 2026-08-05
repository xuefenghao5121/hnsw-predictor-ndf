# Commit Ledger

| date | code_commit | ndf_commit | proposals | clauses | protocol | note |
|------|-------------|------------|-----------|---------|----------|------|
| 2026-08-05 | 3258ce0 | 3258ce0 | proposal-multi-thread-scaling.md | none | CON-SLA-014 | POC topic created; SIFT1M scaling sweep; FineRerank race fix |
| 2026-08-05 | 1531316 | 1531316 | proposal-multi-thread-scaling.md | none | CON-SLA-014 | DEEP10M scaling sweep; 4T peak, 8T+ regression |
| 2026-08-05 | b43db9a | b43db9a | proposal-multi-thread-scaling.md | none | drop_caches (no cgroup) | v2: hnswlib unlimited memory baseline |
| 2026-08-05 | 1d14de7 | 1d14de7 | proposal-promote-finererank-threadsafe.md | BEH-001,BEH-007,BEH-002 | CON-SLA-014 | Promoted: FineRerank race fix + MT benchmark -> Trunk src/ |

## 2026-08-05 promote (A2+C2)

| code_commit | ndf_commit | proposals | clauses | note |
|-------------|------------|-----------|---------|------|
| (pending) | efa919b | proposal-promote-mt-scaling.md | BEH-027, API-013, CON-SLA-017, DEC-074 | A2+C2 promoted. Peak 30332 QPS (16T). |

> source: poc/multi-thread-scaling/ndf/TOPIC.md ; evidence/a2-lockless-bg-20260805.md ; comprehensive-sweep-20260805.md
> track: promote ; Topic: multi-thread-scaling
