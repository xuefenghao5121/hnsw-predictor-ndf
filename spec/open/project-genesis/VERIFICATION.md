# Project Genesis VERIFICATION (adopt)

> track: bootstrap
> bootstrap_mode: adopt
> status: draft
> source_ref: spec/40-constraints/sla.md; spec/50-verification/acceptance.md; spec/50-verification/golden-baseline.md
> architecture_ref: spec/open/project-genesis/ARCHITECTURE.md
> architecture_review_sha: 77622c30cf5dd8097d1bb3b43c061eeab5f9473570b14bf15837eecd505fb5f2

This file is the Genesis **VERIFICATION review** for adopt. Product SLA / verification SoT
remains `spec/40-constraints/` and `spec/50-verification/`. This hop MUST NOT mint new
`{#CON-SLA-*}` / `{#VER-*}` clauses, MUST NOT rewrite those trees, MUST NOT invent
performance goldens, and MUST NOT rewrite git history ([[META-009]] / [[META-006]]).

Project-goal goldens (Charter + Genesis decision + git SHA) are a different object from
the performance Golden Baseline ([[META-009]]).

## Observed SLA / honesty protocol

Inventory only (not rewritten). Authoritative numbers stay in the cited product files.

| Path | Core IDs (sample) | Role |
|------|-------------------|------|
| `spec/40-constraints/sla.md` | `{#CON-HONEST-002}`, `{#CON-SLA-011}`, `{#CON-SLA-014}`, `{#CON-SLA-019}`, `{#CON-SLA-020}`, `{#CON-GOLDEN-001}` | honest I/O, cgroup isolation, sustained SLA, golden config pointer |
| `spec/40-constraints/constants.md` | constants / knobs | measurement constants |
| `spec/meta/constraints.md` | `{#CON-POC-001}` | POC numbers MUST NOT enter Trunk SLA |

Explore/deprecated SLA rows (`{#CON-SLA-012}`, `{#CON-SLA-013}`, `{#CON-SLA-009}`) stay as in product SoT; adopt does not revive them.

## Observed verification protocol

| Path | Core IDs (sample) | Role |
|------|-------------------|------|
| `spec/50-verification/acceptance.md` | `{#VER-001}`…`{#VER-007}` | unit/integration / benchmark correctness |
| `spec/50-verification/acceptance-p2.md` | `{#VER-034}`…`{#VER-044}` | later isolation / SLA acceptance |
| `spec/50-verification/golden-baseline.md` | index only | thin pointer to current `bl-trunk-golden-*` |

Current golden index (observed pointer, not re-measured in this hop):
`spec/50-verification/golden-baseline.md` names `bl-trunk-golden-7ee4ee2` /
`7ee4ee2b0af04feb154abcfd528feabe1557e073`. Genesis MUST NOT copy QPS/recall tables
into this review as new must values.

## Adopt constraints for this VERIFICATION

1. Existing SLA and VER files are the observed protocol; this review confirms them for Genesis provenance.
2. New performance values without evidence stay `draft` / `TBD` / `not-established`.
3. Trunk `src/` / `include/` / `tests/` are **not** written in this hop.
4. `FOUNDATION.md` and genesis-pack wait for `可以建立初始主线`.
5. Daily Product/Topics remain available; adopt MUST NOT block existing POC work.

## Gaps deferred to later Genesis gates

| Later gate | Deferred work |
|------------|----------------|
| `可以建立初始主线` | Foundation matrix + genesis-pack (adopt does not rebuild Trunk) |
| `GENESIS已审核` | `spec/decisions/dec-project-genesis.md` binding IDEA / NDF SHA / Trunk SHA / verification ref |

## Gate

VERIFICATION 已写好：`spec/open/project-genesis/VERIFICATION.md`（产品 SoT 仍为 `spec/40-constraints/` 与 `spec/50-verification/`）。请审阅，回复「VERIFICATION已审核」。

MUST NOT dispatch genesis-pack or write `FOUNDATION.md` until that receipt exists in Genesis `GATES.md`.
