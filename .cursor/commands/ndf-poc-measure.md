---
description: Run bounded POC measurement and write DELTA numbers
---

# /ndf-poc-measure

## Description

Test space repair when gap `numbers_pending` exists. Requires a valid
implementation gate and a complete perf bind skeleton (`vs` / `config_id` /
`measure_script`). Extracted from actions.md Repair with Claude Code.

## Parameters

- `topic` (required)

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py repair-pack --topic <topic> --task poc_measurement --json
```

## Outputs

- `poc/<topic>/ndf/DELTA.md` and `poc/<topic>/ndf/PERF_BASELINE.md` numbers/evidence
- repair-pack JSON + Claude Code completion receipts

## Must not write

- `spec/meta/`, `src/`
- binder gate approvals

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/poc-measure.md`.
Delegate: acp-delegate.md bounded POC repair.
