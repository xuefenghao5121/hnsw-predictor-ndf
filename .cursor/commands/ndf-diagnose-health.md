---
description: Run spec-health and/or topic-health without repairing
---

# /ndf-diagnose-health

## Description

Read-only health. Control uses `spec-health`. Topics Diagnose uses
`spec-health` then `topic-health`. Do not repair. Extracted from actions.md.

## Parameters

- Control: no topic
- Topics: `--topic <topic>`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py spec-health --json
python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic <topic> --json
```

Use the CLI named by the catalog `tool=` line for this dispatch.

## Outputs

- `tmp/ndf-workflow-health/spec.json` and/or `tmp/ndf-workflow-health/topic-*.json`

## Must not write

- `spec/`, `poc/`, `.openclaw/state.json`

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/diagnose-health.md`.
Plane-route findings; do not treat product/binder failures as process proposals.
