# Canvas / commander actions

The React+D3 commander MAY only render ids from
[`spec/meta/cockpit/action-registry.json`](../../../spec/meta/cockpit/action-registry.json).
Enablement comes from snapshot `enabledActions`. This file is an **index**:
id → slash Command → workflow Skill → unique CLI. Semantics live in the
Command file, the Skill, and `spec/meta/tools`. Do not invent Golden / gate /
freshness rules here.

`projection_only` and `openFile` have no Command. Closed-catalog enablement
remains the SoT.

Any mutating hop MUST wrap:

```text
action-begin → operation → action-commit → action-finish
→ snapshot --out tmp/ndf-canvas-snapshot.json
```

`action-commit` stages registry `mayWrite`, commits `ndf-action: <catalog_action_id>`
when dirty (skip if clean), and records Replay A→B. A project `stop` hook may
re-run the same commit idempotently if the Agent omitted it.

Copied prompts start with `/ndf-…`, `skill=…`, `tool=…`, then
`catalog_action_id=<id>`, NDF GIT INPUT, and the concrete wrap including
`action-commit`. There is no `Follow actions.md` fallback. Buttons only copy
the Prompt; humans paste into an Agent. A project `stop` hook may idempotently
re-run `action-commit` + snapshot.

Human phrases stay META-010: **已确认** / **TOPIC已审核** / **可以开始实现**
(and **已审核** / **IDEA已审核** where catalogued). Not 同意 / ok.

## Index

| id | Command | Skill | Unique CLI |
|----|---------|-------|------------|
| `new-proposal` | `/ndf-proposal-generate` | [workflows/proposal-generate.md](workflows/proposal-generate.md) | `control-pack --task control_proposal` |
| `gate-pipeline` | `/ndf-gate-pipeline` | [workflows/gate-pipeline.md](workflows/gate-pipeline.md) | `control-pack --task gate_pipeline` |
| `design-prepare` | `/ndf-binder-pipeline` | [workflows/binder-pipeline.md](workflows/binder-pipeline.md) | `control-pack --task binder_pipeline --focus-binder-facet design` |
| `binder-pipeline` | `/ndf-binder-pipeline` | [workflows/binder-pipeline.md](workflows/binder-pipeline.md) | `control-pack --task binder_pipeline` |
| `binder-amend` | `/ndf-binder-pipeline` | [workflows/binder-pipeline.md](workflows/binder-pipeline.md) | `control-pack --task binder_amend` |
| `generate-next-step` | `/ndf-close-hop` | [workflows/close-hop.md](workflows/close-hop.md) | `ndf_close.py plan` |
| `next-close-hop` | `/ndf-close-hop` | [workflows/close-hop.md](workflows/close-hop.md) | `ndf_close.py plan` |
| `delegate-poc` | `/ndf-poc-delegate` | [workflows/poc-delegate.md](workflows/poc-delegate.md) | `pack` |
| `prepare-acp-lease` | `/ndf-poc-delegate` | [workflows/poc-delegate.md](workflows/poc-delegate.md) | `lease-record` |
| `poc-measurement` | `/ndf-poc-measure` | [workflows/poc-measure.md](workflows/poc-measure.md) | `repair-pack --task poc_measurement` |
| `poc-prepare-baseline` | `/ndf-poc-baseline` | [workflows/poc-baseline.md](workflows/poc-baseline.md) | `repair-pack --task poc_prepare_baseline` |
| `poc-isolation-repair` | `/ndf-poc-isolation` | [workflows/poc-isolation.md](workflows/poc-isolation.md) | `repair-pack --task poc_isolation_repair` |
| `inspect-ledger` | `/ndf-episode-inspect` | [workflows/episode-inspect.md](workflows/episode-inspect.md) | `snapshot --replay-episode` (hidden; focus button-action) |
| `command-replay-run` | `/ndf-command-replay-run` | [workflows/command-replay-run.md](workflows/command-replay-run.md) | `ndf_replay.py command-replay --button-action` |
| `command-replay-compare` | `/ndf-command-replay-compare` | [workflows/command-replay-compare.md](workflows/command-replay-compare.md) | `command-replay --compare-only` |
| `diagnose-advisor` | `/ndf-diagnose-drift` | [workflows/diagnose-drift.md](workflows/diagnose-drift.md) | `ndf_advise.py plan` |
| `run-ndf-control-check` | `/ndf-diagnose-health` | [workflows/diagnose-health.md](workflows/diagnose-health.md) | `spec-health --json` |
| `diagnose-topic` | `/ndf-diagnose-health` | [workflows/diagnose-health.md](workflows/diagnose-health.md) | `topic-health` |
| `align-golden` | `/ndf-golden-align` | [workflows/golden-align.md](workflows/golden-align.md) | `action-begin --operation align-golden` |
| `new-genesis` | `/ndf-genesis` | [workflows/genesis.md](workflows/genesis.md) | `genesis-status --json` |
| `submit-process-improvement` | `/ndf-process-improve` | [workflows/process-improve.md](workflows/process-improve.md) | `project-control-pack --task ndf_improvement_proposal` |
| `repair-kernel` | `/ndf-process-improve` | [workflows/process-improve.md](workflows/process-improve.md) | `project-control-pack --task ndf_improvement_proposal` |
| `land-confirm` | `/ndf-process-land` | [workflows/process-land.md](workflows/process-land.md) | `project-control-pack --task ndf_improvement_land` |
| `land-review` | `/ndf-process-land` | [workflows/process-land.md](workflows/process-land.md) | `project-control-pack --task ndf_improvement_land` |
| `guest-replay-hop` | `/ndf-guest-replay` | [workflows/guest-replay.md](workflows/guest-replay.md) | `guest-run` (optional; Commander hidden) |
| `guest-replay-prefix` | `/ndf-guest-replay` | [workflows/guest-replay.md](workflows/guest-replay.md) | `guest-run` (optional; Commander hidden) |
| `command-replay` (CLI) | — | — | `ndf_replay.py command-replay --button-action` / `--episode` |
| `action-commit` (CLI) | — | — | `ndf_workflow_status.py action-commit` (before snapshot) |
| `refresh-snapshot` | `/ndf-snapshot-refresh` | [workflows/snapshot-refresh.md](workflows/snapshot-refresh.md) | `snapshot` (optional `--probe-runtime`) |
| `open-workbench` | `/ndf-workbench-open` | [workflows/workbench-open.md](workflows/workbench-open.md) | `snapshot --topic` |
| `refresh-topic` | `/ndf-topic-refresh` | [workflows/topic-refresh.md](workflows/topic-refresh.md) | `snapshot --topic` |

Command atoms: [`.cursor/commands/ndf-*.md`](../../commands/).
Human mapping table: [`docs/ndf-button-skills.md`](../../../docs/ndf-button-skills.md).

## Delegates (reuse, do not duplicate)

- Control / gate / binder / process: [openclaw-delegate.md](openclaw-delegate.md)
- POC implementation / baseline / measure / isolation: [acp-delegate.md](acp-delegate.md)
- Close hops: [close-console.md](close-console.md)
- Genesis: [genesis.md](genesis.md)
