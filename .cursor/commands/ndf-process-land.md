---
description: Land a process proposal after the exact human phrase
---

# /ndf-process-land

## Description

Focused process hop CTA. `project-control-pack --task ndf_improvement_land`.
Confirm hop lands `spec/meta/` after **已确认**; review hop only marks the
proposal reviewed after **已审核**. Button click is not approval.
Extracted from actions.md.

## Parameters

- `--proposal <path>`
- `--episode` (required)
- human phrase: 已确认 or 已审核

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack --task ndf_improvement_land --proposal <path> --episode <id> --json
```

## Outputs

- landed `spec/meta/` (confirm) or reviewed proposal header (review)
- OpenClaw request/response receipts

## Must not write

- `.openclaw/state.json` from Cursor
- stable META without **已确认**
- invented human phrases

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/process-land.md`.
