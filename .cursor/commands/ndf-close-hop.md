---
description: Record selected_decision and run the first legal close hop
---

# /ndf-close-hop

## Description

Topics decision hop. Map human text to `selected_decision`. Empty MUST NOT
default to `continue_exploring`. Close modes `{reject, promote, partial}` then
run `ndf_close.py plan` / close-apply. Not silent promote. Extracted from
actions.md and close-console.md.

## Parameters

- `topic` (required)
- `selected_decision`: implement | continue_exploring | reject | promote | partial
- `mode` for close-plan when a close decision is selected

## Unique CLI

```bash
python3 spec/meta/tools/ndf_close.py plan --topic <topic> --mode <promote|partial|reject>
```

JSON wrapper: `python3 spec/meta/tools/ndf_workflow_status.py close-plan --topic <topic> --mode <mode> --json`

## Outputs

- `poc/<topic>/ndf/TOPIC.md` selected_decision hop
- close plan (read-only; no apply)
- first legal close hop in the same chat after **已审核**

## Must not write

- `.openclaw/state.json` as SoT
- invented human phrases
- "open the Close page" (there is no Close tab)

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/close-hop.md`.
This command does not delegate implementation. Promote is never silent.
