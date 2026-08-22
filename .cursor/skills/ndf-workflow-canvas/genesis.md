# Project Genesis

Genesis is the **first step of a new project**: install the full NDF process
profile and meta workflow into this repo (`track=bootstrap`, [[META-009]]).
It lives only on **NDF Control**, always as the first module. It is not a
Product entry and not a late Control afterthought.

Once a product Charter exists, the Canvas still defaults to Product. Without a
Charter, the default tab is NDF Control so initialization starts at Genesis.

## Modes

- `greenfield`: raw IDEA, no usable product Trunk. Control shows an expanded
  G0→G3 安装轨; **New Genesis** is the primary action.
- `adopt`: existing code without accepted local NDF Genesis.
- `operational` + accepted: Control collapses Genesis to 「内核已绑定」
  (`accepted`, `genesis_trunk_sha`). Expand shows kernel capability legend
  (G0–G3 enablement), not product docs or four Open-file cards. New Genesis
  is disabled; do not re-run.
- `operational_legacy`: same collapsed default; daily Product/Topics remain
  available and adopt is optional. Do not treat G0–G3 as a daily workbench.

## G0 IDEA

Use `spec/meta/templates/genesis/IDEA.md.stub`.
Preserve `idea_verbatim`; separate user statements from deductions. After a valid
`IDEA已审核` receipt, draft Charter and Foundation.

## G1 Foundation

Use `spec/meta/templates/genesis/FOUNDATION.md.stub`.

Required gates:

```text
CHARTER已审核 → ARCHITECTURE已审核 → VERIFICATION已审核
→ 可以建立初始主线
```

No evidence-backed performance value means `draft|TBD|not-established`.

## G2 Trunk Candidate

Run:

```bash
python3 spec/meta/tools/ndf_workflow_status.py genesis-pack \
  --mode greenfield|adopt --json
```

Only dispatch when `safe_to_dispatch=true`. Claude Code creates the smallest buildable
vertical slice in an isolated worktree. Unknown mechanisms become later POCs.

## G3 Freeze

Use `spec/meta/templates/genesis/GENESIS_DEC.md.stub`.

Require:

- valid Foundation receipts
- NDF index and graphcheck
- build and minimum acceptance
- Design→Implementation→Test traceability
- candidate commit and reproducible commands
- resolvable NDF/Trunk SHAs

After `GENESIS已审核`, mark the Genesis decision accepted. Control keeps Genesis
first as the installed binding; kernel map / self-consistency / process evolution
become the daily Control surface. Never rewrite Genesis history.
