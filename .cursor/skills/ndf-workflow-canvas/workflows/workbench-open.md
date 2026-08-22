# Workbench open workflow

Orchestrates `/ndf-workbench-open`. Catalog id: `open-workbench`.

## Command

`/ndf-workbench-open`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py snapshot --out tmp/ndf-canvas-snapshot.json --json
```

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. `snapshot --out tmp/ndf-canvas-snapshot.json --topic <id> --json` (no `--probe-runtime`).
3. Rebuild standalone commander. MUST NOT write `spec/` or `poc/`.
