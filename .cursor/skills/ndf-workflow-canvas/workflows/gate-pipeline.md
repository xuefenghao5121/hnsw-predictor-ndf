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
Command Agent builds `control-pack`, waits for human 「派发」, then runs `dispatch-send`.

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Prefer `--resume` when the gate Episode is active.
3. `control-pack --task gate_pipeline --json` then report summary.
4. If not safe: finish cancelled + snapshot; stop. If safe: wait for human 「派发」.
5. `dispatch-send` → OpenClaw → wait response → completion → action-commit → action-finish → snapshot.
6. OpenClaw (worker): each gate drafts `GATES.md` pending rows; MUST NOT set `approved_by`. Wait for the exact human phrase.
7. Missing binder facet → `blocked_by_binder` + `next_binder_facet`; hand off to `/ndf-binder-pipeline`. Gate MUST NOT create binder files.
8. All three valid → `decision_required`, not automatic close.

Button click is not approval. `sent` / `acknowledged` is not success.
