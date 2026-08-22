---
description: Generate one NDF product proposal from exact human intent
---

# /ndf-proposal-generate

## Description

Product idea entry. Write the exact human utterance to a gitignored intent file,
then run control-pack. OpenClaw drafts one `spec/open/proposal-*.md` and stops
at **已确认**. Extracted from `.cursor/skills/ndf-workflow-canvas/actions.md`
(New Proposal). Does not invent Golden/gate/freshness rules.

## Parameters

- `intent` (required): exact human product utterance. Empty MUST NOT dispatch
  and MUST NOT let the Agent invent an idea.
- `intent-file`: `tmp/ndf-product-intent-<action_id>.md`
- no `--topic` (this hop has no existing topic)

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py control-pack --task control_proposal --intent-file <tmp-file> --json
```

## Outputs

- `spec/open/proposal-*.md` with `Status: Pending confirmation`
- control-pack JSON + OpenClaw request/response receipts

## Must not write

- `poc/` before **已确认**
- `spec/meta/` or `spec/meta/open/` (process stays on Control 提交流程改进)
- `.openclaw/state.json` from Cursor
- human phrases `已确认` / `TOPIC已审核` / `可以开始实现`

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/proposal-generate.md`.
Delegate template: `.cursor/skills/ndf-workflow-canvas/openclaw-delegate.md`.
Human phrase remains **已确认**, not 同意/ok.
