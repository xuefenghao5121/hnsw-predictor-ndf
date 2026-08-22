---
description: Start the three-gate OpenClaw pipeline for the focused topic
---

# /ndf-gate-pipeline

## Description

Atomic control-pack for pipeline A (闸 only). Three ordered gates:
TOPIC已审核 → DESIGN已审核 → 可以开始实现. Gate owns only `GATES.md`.
Extracted from actions.md and openclaw-delegate.md. Do not merge with binder.

## Parameters

- `topic` (required): focused topic id
- `--resume` when `control_pipelines.gate.resume` is true
- `--focus-gate` to resume one gate

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py control-pack --topic <topic> --task gate_pipeline --json
```

## Outputs

- `poc/<topic>/ndf/GATES.md` pending/invalidated rows (never `approved_by` from Agent)
- control-dispatch + ndf-agent-message receipts
- `next_human_phrase` for the current gate

## Must not write

- binder files (`TOPIC`/`DESIGN`/`PERF_BASELINE`/`DELTA`/`INTERFACE`/`COMMITS`)
- `spec/meta/`, `src/`, `.openclaw/state.json` from Cursor
- forged `approved_by`

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/gate-pipeline.md`.
Actual `openclaw.chat_send` is required. Composer creation alone is not acknowledged.
Button click is not approval; wait for the exact human phrase.
