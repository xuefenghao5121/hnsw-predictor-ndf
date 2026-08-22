---
description: Read-only advisor plan for graph/bind drift
---

# /ndf-diagnose-drift

## Description

First spec-health, then read-only `ndf_advise plan`. Never apply. Never
recommend copying product clauses or POC binder fields into `spec/meta/`.
Extracted from actions.md Diagnose with Advisor.

## Parameters

- `--surface graph|bind` (advise)
- optional `--meta`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_advise.py plan --surface graph --low-hanging-fruit
```

## Outputs

- `tmp/` advise report (surgery options). No SoT writes.

## Must not write

- `spec/`, `poc/`, `.openclaw/state.json`

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/diagnose-drift.md`.
If binder_health is n/a, do not route to Topics.
