# Commander button → Command / Skill

Closed catalog: [`spec/meta/cockpit/action-registry.json`](../spec/meta/cockpit/action-registry.json).
Enablement stays snapshot-derived. Command files are atoms under
[`.cursor/commands/`](../.cursor/commands/). Skills orchestrate under
[`.cursor/skills/ndf-workflow-canvas/workflows/`](../.cursor/skills/ndf-workflow-canvas/workflows/).
Index: [`.cursor/skills/ndf-workflow-canvas/actions.md`](../.cursor/skills/ndf-workflow-canvas/actions.md).

Copied prompts start with:

```text
/ndf-poc-baseline
skill=.cursor/skills/ndf-workflow-canvas/workflows/poc-baseline.md
tool=python3 spec/meta/tools/ndf_workflow_status.py repair-pack --task poc_prepare_baseline
```

then the existing NDF GIT INPUT block. There is no `Follow actions.md` fallback.
Human phrases remain META-010 (`已确认` / `TOPIC已审核` / `可以开始实现`), not 同意/ok.

This round does **not** add WebSocket auto-refresh. After the local Agent runs,
rebuild `tmp/ndf-canvas-snapshot.json` and `docs/ndf-commander.html` (or Refresh
on a machine-local `--serve`).

Do not treat [`packages/ndf-harness/`](../packages/ndf-harness/) as local process truth.

## Idea button → existing action

| idea button | action_id | Command | Skill / tool |
| ----------- | --------- | ------- | ------------ |
| 生成提案 | `new-proposal` | `/ndf-proposal-generate` | `control-pack --task control_proposal` |
| 审批 Gate | `gate-pipeline` | `/ndf-gate-pipeline` | three gates + [openclaw-delegate.md](../.cursor/skills/ndf-workflow-canvas/openclaw-delegate.md) |
| 装订 | `binder-pipeline` / `binder-amend` | `/ndf-binder-pipeline` | six facets + openclaw-delegate |
| 晋升 POC | `next-close-hop` + `generate-next-step` | `/ndf-close-hop` | `ndf_close.py plan` / `selected_decision` — not silent promote |
| 委派实现 | `delegate-poc` / `prepare-acp-lease` | `/ndf-poc-delegate` | `pack` + [acp-delegate.md](../.cursor/skills/ndf-workflow-canvas/acp-delegate.md) |
| 运行验证 | `poc-measurement` | `/ndf-poc-measure` | `repair-pack --task poc_measurement` |
| 基线 | `poc-prepare-baseline` | `/ndf-poc-baseline` | `repair-pack --task poc_prepare_baseline` |
| 查看历史 / 详情 | `inspect-ledger` | `/ndf-episode-inspect` | `snapshot --replay-episode` |
| 漂移检测 | `diagnose-advisor` | `/ndf-diagnose-drift` | `ndf_advise.py` (read-only) |
| 健康检查 | `run-ndf-control-check` / `diagnose-topic` | `/ndf-diagnose-health` | `spec-health` / `topic-health` |

## Remaining composer / snapshot buttons

| action_id | Command | Skill / tool |
| --------- | ------- | ------------ |
| `align-golden` | `/ndf-golden-align` | `action-begin --operation align-golden` |
| `new-genesis` | `/ndf-genesis` | `genesis-status --json` |
| `submit-process-improvement` / `repair-kernel` | `/ndf-process-improve` | `project-control-pack --task ndf_improvement_proposal` |
| `land-confirm` / `land-review` | `/ndf-process-land` | `project-control-pack --task ndf_improvement_land` |
| `guest-replay-hop` / `guest-replay-prefix` | `/ndf-guest-replay` | `ndf_replay.py guest-run --adapter vm` |
| `refresh-snapshot` | `/ndf-snapshot-refresh` | `snapshot --probe-runtime` |
| `open-workbench` | `/ndf-workbench-open` | `snapshot --topic` |
| `refresh-topic` | `/ndf-topic-refresh` | `snapshot --topic` |
| `poc-isolation-repair` | `/ndf-poc-isolation` | `repair-pack --task poc_isolation_repair` |

`projection_only` and `openFile` are not Commands.

Idea source (unmodified): [`docs/new_idea.md`](new_idea.md).
