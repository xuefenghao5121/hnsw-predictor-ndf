---
description: Align Golden matrix or mark docs-only ahead
---

# /ndf-golden-align

## Description

Product-only. If Trunk `src/include/tests` changed since Golden, re-run the
Golden matrix. Docs/process/poc only: do not re-run; refresh snapshot until
`docs_only_ahead`. Extracted from actions.md Align Golden.

## Parameters

- none beyond GIT INPUT remote_branch

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py action-begin --operation align-golden
```

Then `git diff --name-only <golden> HEAD -- src include tests`.

## Outputs

- `baselines/bl-trunk-golden-<head>.md` and `golden-baseline.md` when Trunk source changed
- snapshot refresh when docs-only

## Must not write

- `.openclaw/state.json`

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/golden-align.md`.
