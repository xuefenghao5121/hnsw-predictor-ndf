# Golden align workflow

Orchestrates `/ndf-golden-align`. Catalog id: `align-golden`.

## Command

`/ndf-golden-align`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py action-begin --operation align-golden
```

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Unique CLI.
3. `git diff --name-only <golden> HEAD -- src include tests`.
4. Trunk source changed → re-run Golden matrix; write `baselines/bl-trunk-golden-<head>.md`; update `golden-baseline.md`.
5. Docs/process/poc only → do not re-run; refresh snapshot until `docs_only_ahead` unblocks New Proposal.
6. `action-finish` + snapshot `--out tmp/ndf-canvas-snapshot.json`.
