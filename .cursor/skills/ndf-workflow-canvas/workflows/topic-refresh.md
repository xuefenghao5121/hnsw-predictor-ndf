# Topic refresh workflow

Orchestrates `/ndf-topic-refresh`. Catalog id: `refresh-topic`.

## Command

`/ndf-topic-refresh`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py snapshot --out tmp/ndf-canvas-snapshot.json --json
```

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. `snapshot --out tmp/ndf-canvas-snapshot.json --topic <focused> --json` (no `--probe-runtime`).
3. Rebuild standalone commander.
