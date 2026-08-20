---
description: Prepare the isolated POC baseline workspace
---

# /ndf-poc-baseline

## Description

Implementation space repair when gap `missing_baseline_workspace` exists.
Copy INTERFACE implementation slice and required Trunk baseline `.h/.cpp`
into `poc/<topic>/`. Extracted from actions.md Repair with Claude Code.

## Parameters

- `topic` (required)

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py repair-pack --topic <topic> --task poc_prepare_baseline --json
```

## Outputs

- buildable R0-aligned workspace under `poc/<topic>/`

## Must not write

- `src/`, `include/`, `tests/`, `spec/meta/`
- PERF Numbers / DELTA / measurement
- git history rewrite
- `.openclaw/state.json` from Cursor

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/poc-baseline.md`.
