# Diagnose drift workflow

Orchestrates `/ndf-diagnose-drift`. Catalog id: `diagnose-advisor`.
Read-only. Does not apply surgery.

## Command

`/ndf-diagnose-drift`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_advise.py plan
```

## Sequence

1. GIT INPUT checkout of `remote_branch` (read-only; no git mutation required beyond the contract).
2. `python3 spec/meta/tools/ndf_workflow_status.py spec-health --json`
3. `python3 spec/meta/tools/ndf_advise.py plan --surface graph --low-hanging-fruit` (and bind surface as needed).
4. Never apply. Never copy product clauses or POC binder fields into `spec/meta/`.
5. If binder_health is n/a, do not route to Topics.
