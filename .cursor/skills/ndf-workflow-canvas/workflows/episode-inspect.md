# Episode inspect workflow

Orchestrates `/ndf-episode-inspect`. Catalog id: `inspect-ledger`.
Episode list remains the Replay projection; this hop focuses one ledger page.

## Command

`/ndf-episode-inspect`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py snapshot --replay-episode
```

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. `action-begin --operation inspect-ledger`
3. `snapshot --out tmp/ndf-canvas-snapshot.json --replay-episode <id> --json` (no `--probe-runtime`).
4. `python3 spec/meta/cockpit/build_standalone.py`
5. `action-finish`. MUST NOT write `spec/` or `poc/`.
