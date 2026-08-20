# POC baseline workflow

Orchestrates `/ndf-poc-baseline`. Catalog id: `poc-prepare-baseline`.

## Command

`/ndf-poc-baseline`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py repair-pack --task poc_prepare_baseline
```

## Delegate

Claude Code via [acp-delegate.md](../acp-delegate.md) bounded POC repair.

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. `action-begin --operation poc_prepare_baseline`
3. `repair-pack --topic <t> --task poc_prepare_baseline --json`
4. Copy INTERFACE slice + required Trunk baseline `.h/.cpp` into `poc/<topic>/`.
5. MUST NOT measure, MUST NOT amend PERF Numbers/DELTA, MUST NOT touch Trunk `src/`/`include/`/`tests/` or rewrite git history.
6. `action-finish` + snapshot `--out tmp/ndf-canvas-snapshot.json`.
