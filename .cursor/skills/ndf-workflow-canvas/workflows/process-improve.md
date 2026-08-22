# Process improve workflow

Orchestrates `/ndf-process-improve`. Catalog ids: `submit-process-improvement`, `repair-kernel`.

## Command

`/ndf-process-improve`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack --task ndf_improvement_proposal
```

## Delegate

OpenClaw via [openclaw-delegate.md](../openclaw-delegate.md).
Command Agent prepares pack, waits for human 「派发」, then `dispatch-send`.

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Human-intent: write exact META intent to `tmp/ndf-process-intent-<action_id>.md`; `--origin human_intent --intent-file`.
3. Finding-driven: `--origin health_finding` (requires current spec-health findings).
4. Run unique CLI; report summary; wait for 「派发」; then `dispatch-send` → OpenClaw. Stamp `Status: Pending confirmation`; stop at **已确认**.
5. MUST NOT write stable META, product/POC docs, or `.openclaw/state.json` from Cursor.
6. Next hop is `/ndf-process-land`, not a second intake.
