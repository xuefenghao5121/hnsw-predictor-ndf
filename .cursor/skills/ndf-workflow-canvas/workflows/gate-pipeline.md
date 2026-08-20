# Gate pipeline workflow

Orchestrates `/ndf-gate-pipeline`. Catalog id: `gate-pipeline`.
Three gates stay three gates; do not collapse into one 「审批 Gate」.

## Command

`/ndf-gate-pipeline`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py control-pack --topic <topic> --task gate_pipeline --json
```

## Delegate

OpenClaw via [openclaw-delegate.md](../openclaw-delegate.md) pipeline A (闸).
Ordered: TOPIC已审核 → DESIGN已审核 → 可以开始实现.

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Prefer `--resume` when the gate Episode is active.
3. control-pack `gate_pipeline`; record requested → sent → acknowledged.
4. Actual MCP `openclaw.chat_send` with the gate_pipeline template.
5. Each gate: draft `GATES.md` pending rows; MUST NOT set `approved_by`. Wait for the exact human phrase.
6. Missing binder facet → `blocked_by_binder` + `next_binder_facet`; hand off to `/ndf-binder-pipeline`. Gate MUST NOT create binder files.
7. All three valid → `decision_required`, not automatic close.
8. `topic-health` + snapshot refresh. This round does not WebSocket-push.

Button click is not approval.
