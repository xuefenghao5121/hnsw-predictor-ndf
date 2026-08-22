---
description: Guest-VM replay a hop or selected timeline prefix
---

# /ndf-guest-replay

## Description

Host launcher only. `guest-run --adapter vm`. Proof is
`ndf-replay-guest-proof/v1` (`valid=true`, contract `adapter=vm`).
Extracted from actions.md Guest VM replay.

## Parameters

- `--episode` (required)
- `--commit <sha>`
- prefix variant reports only the selected timeline prefix

## Unique CLI

```bash
python3 spec/meta/tools/ndf_replay.py guest-run --adapter vm --episode <id> --commit <sha>
```

## Outputs

- guest-proof JSON; `environment_blocked` if no KVM/image (no soft fallback)

## Must not write

- host-mount of live `repo_root`
- `src/`
- re-dispatch of recorded context onto the live checkout

## Notes

Orchestration: `.cursor/skills/ndf-workflow-canvas/workflows/guest-replay.md`.
