---
description: Repair POC isolation inside poc/<topic>/
---

# /ndf-poc-isolation

## Description

Implementation space repair only when a matching isolation finding exists.
May run while normal `pack.safe_to_dispatch=false`. Confined to `poc/<topic>/`.
Extracted from actions.md.

## Parameters

- `topic` (required)

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py repair-pack --topic <topic> --task poc_isolation_repair --json
```

## Outputs

- isolation repair inside `poc/<topic>/`
- topic-health recheck inputs

## Must not write

- `src/`
- git history (disposition needs human approval)

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/poc-isolation.md`.
