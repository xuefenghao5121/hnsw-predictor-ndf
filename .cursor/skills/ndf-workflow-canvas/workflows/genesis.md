# Genesis workflow

Orchestrates `/ndf-genesis`. Catalog id: `new-genesis`.
Detail: [genesis.md](../genesis.md). NDF Control only.

## Command

`/ndf-genesis`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py genesis-status --json
```

## Delegate

OpenClaw for the IDEA draft; Claude Code `genesis-pack` only after Foundation gates (not this button).

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Unique CLI. Disabled when Genesis is already accepted.
3. Draft `spec/open/proposal-project-genesis.md` track=bootstrap.
4. Stop at **IDEA已审核**. MUST NOT write stable `spec/meta/` or `poc/`.
5. Snapshot refresh. Never show this hop on Product.
