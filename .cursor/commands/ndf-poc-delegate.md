---
description: Pack and delegate POC implementation, or prepare an ACP lease
---

# /ndf-poc-delegate

## Description

Atomic pack / lease-record for Claude Code POC work. Delegate only when
`static_preflight_passed` and **active isolated lease** (`run_id` + worktree).
If no lease yet, run Prepare ACP lease first. Extracted from actions.md and
acp-delegate.md.

## Parameters

- `topic` (required)
- `episode` (required)
- variant: `pack` (Delegate POC) or `lease-record` (Prepare ACP lease)

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py pack --topic <topic> --episode <id> --json
python3 spec/meta/tools/ndf_workflow_status.py lease-record --file tmp/lease.json --episode <id> --json
```

Use exactly one of those per dispatch.

## Outputs

- pack JSON with workspace.repo_root, manifest_sha, context_plan.plan_sha
- lease receipt in `tmp/ndf-workflow-leases.jsonl` when preparing
- Claude Code completion + POST_DISPATCH_SYNC when dispatching

## Must not write

- `src/`, `spec/meta/`, `spec/00-50` from the POC worker
- implementation writes during lease-prep
- `.openclaw/state.json` from Cursor

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/poc-delegate.md`.
Human phrase for Delegate POC: **可以开始实现**. Worker markdown is not the
command surface.
