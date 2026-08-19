---
name: ndf-harness
description: >-
  Thin Cursor adapter for the portable NDF Harness. Init/adopt/govern/sync NDF
  norms, AGENTS.md workflow, and review tools. Runtime-agnostic skill core lives
  under packages/ndf-harness/skill/. Use when the user mentions NDF harness,
  NDF 初始化, NDF 治理, or portable NDF.
disable-model-invocation: true
---

# NDF Harness — Cursor adapter（薄）

**Do not treat this file as the workflow SoT.**

Follow, in order:

1. [`packages/ndf-harness/skill/SKILL.md`](../../../packages/ndf-harness/skill/SKILL.md)
2. [`packages/ndf-harness/skill/MODES.md`](../../../packages/ndf-harness/skill/MODES.md)
3. Repo-root / package [`workflow/AGENTS.md`](../../../packages/ndf-harness/workflow/AGENTS.md)
4. [`packages/ndf-harness/adapters/cursor/README.md`](../../../packages/ndf-harness/adapters/cursor/README.md)

Cross-runtime package entry: [`packages/ndf-harness/README.md`](../../../packages/ndf-harness/README.md).  
Governance chain: [`spec/meta/tools/GOVERNANCE.md`](../../../spec/meta/tools/GOVERNANCE.md).  
Distribution notes: [`spec/meta/tools/HARNESS.md`](../../../spec/meta/tools/HARNESS.md).

## Modes（same as core）

`init` | `adopt` | `govern` | `sync`

## Cursor-only notes

- `disable-model-invocation: true` — invoke explicitly（「用 ndf-harness …」）.  
- Never silent-overwrite finalized `AGENTS.md` / `spec/meta`.  
- Never put review tools under product `scripts/`.
