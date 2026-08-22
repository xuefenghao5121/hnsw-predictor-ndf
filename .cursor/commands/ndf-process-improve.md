---
description: Draft an NDF process improvement proposal
---

# /ndf-process-improve

## Description

`project-control-pack --task ndf_improvement_proposal`. Human-intent entry
writes exact META intent to tmp/; finding-driven repair uses
`--origin health_finding`. Draft `spec/meta/open/` and stop at **已确认**.
Extracted from actions.md.

## Parameters

- `--origin human_intent|health_finding`
- `--intent-file` when origin is human_intent
- `--episode` (required)

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack --task ndf_improvement_proposal --origin human_intent --intent-file <tmp-file> --episode <id> --json
```

## Outputs

- `spec/meta/open/proposal-meta-*.md` with `Status: Pending confirmation`

## Must not write

- stable `spec/meta/`
- `spec/00-50`, `poc/`, `.openclaw/state.json` from Cursor
- product clauses or POC binder fields copied into META

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/process-improve.md`.
