# Proposal: Project Genesis (adopt operational_legacy)

> track: bootstrap
> bootstrap_mode: adopt
> status: proposal
> 日期: 2026-08-15
> 关联: [[META-009]], [[META-010]]
> 阶段: IDEA（G0）only

## Classification

`genesis-status` (2026-08-15):

| Field | Value |
|-------|-------|
| `project_maturity` | `operational_legacy` |
| `accepted` | `false` |
| `genesis_trunk_sha` | `null` |
| `clause_count` | 130 |
| Charter | present (`spec/00-charter/`) |
| Trunk `src/` | present |
| warning | Genesis provenance missing; legacy operational project |

`bootstrap_mode=adopt`: existing product tree and Trunk without an accepted Genesis decision.

This is **not** `operational` + accepted. Re-run is therefore allowed as optional adopt. Daily Product/Topics MUST remain unblocked.

## IDEA stage (this hop)

Created:

- `spec/open/proposal-project-genesis.md` (this file)
- `spec/open/project-genesis/IDEA.md` (verbatim observed IDEA + source_ref)

MUST NOT in this hop:

- Charter / Architecture / Verification Foundation bodies
- Genesis `GATES.md` approvals or forged `approved_by`
- Trunk `src/`, `include/`, `tests/`
- `spec/meta/` body
- `spec/decisions/dec-project-genesis.md`

## After `IDEA已审核`

Next hop writes CHARTER (Foundation start) and waits for `CHARTER已审核`. Later serial gates:

```text
IDEA已审核 → CHARTER已审核 → ARCHITECTURE已审核
→ VERIFICATION已审核 → 可以建立初始主线 → GENESIS已审核
```

Adopt later binds observed NDF + Trunk SHAs; MUST NOT rewrite git history. No evidence-backed new performance values; existing SLA/golden stay product SoT.

## Human gate

IDEA 已写好：`spec/open/project-genesis/IDEA.md`（提案：`spec/open/proposal-project-genesis.md`）。请审阅，回复「IDEA已审核」。
