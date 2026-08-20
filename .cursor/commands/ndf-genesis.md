---
description: Draft project Genesis and stop at IDEA已审核
---

# /ndf-genesis

## Description

NDF Control only. `genesis-status --json`; draft
`spec/open/proposal-project-genesis.md` track=bootstrap; stop at **IDEA已审核**.
Disabled when Genesis is already accepted. Extracted from actions.md and genesis.md.

## Parameters

- mode from genesis-status: greenfield | adopt

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py genesis-status --json
```

## Outputs

- `spec/open/proposal-project-genesis.md`

## Must not write

- stable `spec/meta/`
- `poc/`

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/genesis.md`.
Never shown on Product. Human phrase **IDEA已审核**, not 同意/ok.
