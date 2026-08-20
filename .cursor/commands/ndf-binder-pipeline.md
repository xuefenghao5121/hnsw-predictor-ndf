---
description: Start or amend the six-facet binder pipeline for the focused topic
---

# /ndf-binder-pipeline

## Description

Atomic control-pack for pipeline B (面 only). Six facets: TOPIC → DESIGN →
PERF → DELTA → INTERFACE → COMMITS. `binder_amend` revises one focused facet
under the same hypothesis. Extracted from actions.md and openclaw-delegate.md.

## Parameters

- `topic` (required)
- `task`: `binder_pipeline` or `binder_amend`
- `--focus-binder-facet` when amending one facet
- `--resume` when binder Episode is active

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py control-pack --topic <topic> --task binder_pipeline --json
python3 spec/meta/tools/ndf_workflow_status.py control-pack --topic <topic> --task binder_amend --json
```

Use exactly one of those tasks per dispatch.

## Outputs

- amended facet files under `poc/<topic>/ndf/`
- `changed_sections` evidence; complete facets are audit/recheck no-ops

## Must not write

- `GATES.md` approvals / `approved_by`
- `src/`, `spec/meta/`
- PERF Numbers, DELTA Rounds, evidence (those need Claude Code measurement)
- `selected_decision` as `new_poc` (hypothesis change is a new proposal)

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/binder-pipeline.md`.
Do not call 面 “闸”. Do not merge with `/ndf-gate-pipeline`.
