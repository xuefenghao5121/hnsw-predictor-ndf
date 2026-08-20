# Process land workflow

Orchestrates `/ndf-process-land`. Catalog ids: `land-confirm`, `land-review`.

## Command

`/ndf-process-land`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack --task ndf_improvement_land --proposal <path> --episode <id> --json
```

## Delegate

OpenClaw via [openclaw-delegate.md](../openclaw-delegate.md).

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Unique CLI against the focused process proposal path.
3. Actual `openclaw.chat_send`. Wait for the exact human phrase (**已确认** or **已审核**). Button click is not approval.
4. Confirm hop lands `spec/meta/` then waits for **已审核** in the same chat if the human stays.
5. Review hop only marks the proposal reviewed.
6. `action-finish` + snapshot refresh.
