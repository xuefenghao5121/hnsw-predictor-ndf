---
description: Probe in-flight worker without re-dispatching the pack
---

# /ndf-dispatch-probe

## Description

Read-only dispatch probe for an in-flight Claude Code / ACP hop. Use when the
user asks **进展如何** in the commander chat. MUST NOT call `dispatch-send`
again for the same pack.

## Parameters

- optional `--topic <topic>` (focused topic from snapshot)

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py dispatch-probe --json
```

## Outputs

- JSON with transport / receipt / completion state
- Human phrase: **进展如何**

## Must not write

- `poc/`, `src/`, `spec/`, `.openclaw/state.json`
- MUST NOT re-dispatch the ready pack

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/acp-delegate.md`.
Transport acknowledgement is not validated completion; read disk
`ndf-agent-completion/v1` via completion-record when the hop finishes.
