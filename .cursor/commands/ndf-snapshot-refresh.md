---
description: Rebuild the official commander snapshot with runtime probe
---

# /ndf-snapshot-refresh

## Description

Header Refresh snapshot. Official snapshot with `--probe-runtime`. Unchanged
Merkle layers MUST NOT re-run graphcheck. Extracted from actions.md.

## Parameters

- optional `--topic <business-topic>`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py snapshot --out tmp/ndf-canvas-snapshot.json --probe-runtime --json
```

## Outputs

- `tmp/ndf-canvas-snapshot.json`
- rebuilt `docs/ndf-commander.html` via `python3 spec/meta/cockpit/build_standalone.py`

## Must not write

- `spec/`, `poc/`, `.openclaw/state.json`

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/snapshot-refresh.md`.
This round does not add WebSocket auto-refresh.
