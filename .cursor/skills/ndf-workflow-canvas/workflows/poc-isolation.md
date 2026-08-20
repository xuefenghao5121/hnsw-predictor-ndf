# POC isolation workflow

Orchestrates `/ndf-poc-isolation`. Catalog id: `poc-isolation-repair`.

## Command

`/ndf-poc-isolation`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py repair-pack --task poc_isolation_repair
```

## Delegate

Claude Code via [acp-delegate.md](../acp-delegate.md) bounded isolation repair.
Command Agent stops after pack JSON; hook sends ACP.

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Only when a matching isolation finding exists.
3. `repair-pack --topic <t> --task poc_isolation_repair --json` (allowed even if normal pack is not `safe_to_dispatch`).
4. **STOP.** Hook dispatches Claude Code. Repair/copy only inside `poc/<topic>/` on the worker.
   Trunk cleanup or git history needs human approval.
5. Hook closeout: completion → action-commit → snapshot (topic-health via post_checks).
