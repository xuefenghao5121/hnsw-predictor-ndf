# Commit Ledger - l4-cache-mgmt

> [[DEF-023]] / [[BEH-025]]. Append a row for each code/script commit under this topic.
> Historical commits before binder adoption are not backfilled.

| date | code_commit | ndf_commit | proposals | clauses | protocol | note |
|------|-------------|------------|-----------|---------|----------|------|
| 2026-08-03 | - | (binder created) | proposal-l4-cache-mgmt | BEH-024 | CON-SLA-014 / DEC-066 | ledger starts; no code yet |
| 2026-08-03 | 7cdb399 | d9e1b61 | proposal-promote-l4 | BEH-024, DEC-068 | CON-SLA-014 / DEC-067 | promote: flat_vec_cache check + O_DIRECT 4T fix; BEH-024 draft->stable |
| 2026-08-04 | 2f008f7 | 0805b74 | proposal-promote-willneed | BEH-024, API-012, DEC-070 | CON-SLA-014 | promote WILLNEED: 17.9x@256MB, +2.2%@512MB, no regression |
