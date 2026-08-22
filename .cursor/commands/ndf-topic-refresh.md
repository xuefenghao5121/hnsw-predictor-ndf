---
description: Refresh the focused topic snapshot without runtime probe
---

# /ndf-topic-refresh

## Description

Same snapshot builder with `--topic <id>` (no `--probe-runtime`). Lives in
Topics 阻塞与修复 header. Extracted from actions.md.

## Parameters

- `--topic` (required, focused)

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py snapshot --out tmp/ndf-canvas-snapshot.json --topic <topic> --json
```

## Outputs

- `tmp/ndf-canvas-snapshot.json`

## Must not write

- `spec/`, `poc/`, `.openclaw/state.json`

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/topic-refresh.md`.
