---
description: Focus Replay on one episode ledger page
---

# /ndf-episode-inspect

## Description

Replay 「查这条账」. Rebuild snapshot with `--replay-episode`. List stays in
the Replay projection. Extracted from actions.md / SKILL.md.

## Parameters

- `episode` (required): hop id

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py snapshot --out tmp/ndf-canvas-snapshot.json --replay-episode <episode> --json
```

## Outputs

- `tmp/ndf-canvas-snapshot.json` with `replay.focused` set to that hop

## Must not write

- `spec/`, `poc/`, `.openclaw/state.json`

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/episode-inspect.md`.
Do not pass `--probe-runtime`.
