---
description: Open the Topics workbench for a selected topic id
---

# /ndf-workbench-open

## Description

Topics, when selector ≠ `focusedTopicId`. Snapshot with `--topic <id>` and
no `--probe-runtime`. Isomorphic to Replay 「查这条账」. Extracted from actions.md.

## Parameters

- `--topic` (required)

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py snapshot --out tmp/ndf-canvas-snapshot.json --topic <topic> --json
```

## Outputs

- `tmp/ndf-canvas-snapshot.json` focused on that topic

## Must not write

- `spec/`, `poc/`, `.openclaw/state.json`

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/workbench-open.md`.
