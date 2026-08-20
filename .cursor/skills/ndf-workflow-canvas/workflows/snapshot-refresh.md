# Snapshot refresh workflow

Orchestrates `/ndf-snapshot-refresh`. Catalog id: `refresh-snapshot`.
This round does not add WebSocket auto-refresh.

## Command

`/ndf-snapshot-refresh`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py snapshot --out tmp/ndf-canvas-snapshot.json --probe-runtime --json
```

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Unique CLI (header Refresh is the only `--probe-runtime` hop).
3. Unchanged Merkle layers MUST NOT re-run graphcheck.
4. `python3 spec/meta/cockpit/build_standalone.py`
5. MUST NOT write `spec/` or `poc/`.
