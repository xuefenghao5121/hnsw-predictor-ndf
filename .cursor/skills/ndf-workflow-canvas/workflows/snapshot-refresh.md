# Snapshot refresh workflow

Orchestrates `/ndf-snapshot-refresh`. Catalog id: `refresh-snapshot`.
This hop rebuilds the official commander snapshot with `--probe-runtime`.

On a machine running `snapshot --serve` at `http://127.0.0.1:8765`, writing
`tmp/ndf-canvas-snapshot.json` auto-reloads the live page. Do not curl
`localhost:8081`. htmlpreview is static.

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
