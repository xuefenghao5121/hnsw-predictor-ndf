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
**Command Agent only builds the pack.** `afterShellExecution` hook runs `dispatch-send`
when `safe_to_dispatch`. Worker copies live under ACP — not in this Composer chat.

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. `action-begin --operation poc_prepare_baseline --catalog-action-id poc-prepare-baseline`
3. `repair-pack --topic <t> --task poc_prepare_baseline --json`
4. **STOP.** If pack is not `safe_to_dispatch`, report blockers. Do not copy files. Do not invent ACP start.
5. Hook: send Claude Code ACP → wait result → completion-record → action-commit → snapshot.
6. Worker (ACP) copies INTERFACE slice + required Trunk baseline `.h/.cpp` into `poc/<topic>/`.
   MUST NOT measure, MUST NOT amend PERF Numbers/DELTA, MUST NOT touch Trunk `src/`/`include/`/`tests/`.
