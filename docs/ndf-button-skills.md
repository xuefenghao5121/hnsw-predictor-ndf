# Commander button → Command / Skill

Closed catalog: [`spec/meta/cockpit/action-registry.json`](../spec/meta/cockpit/action-registry.json).
Enablement stays snapshot-derived. Command files are atoms under
[`.cursor/commands/`](../.cursor/commands/). Skills orchestrate under
[`.cursor/skills/ndf-workflow-canvas/workflows/`](../.cursor/skills/ndf-workflow-canvas/workflows/).
Index: [`.cursor/skills/ndf-workflow-canvas/actions.md`](../.cursor/skills/ndf-workflow-canvas/actions.md).

Copied prompts start with:
```
/ndf-…
skill=…
tool=…
```

then `catalog_action_id=<id>`, `BEGIN NDF GIT INPUT`, and a concrete wrap including
`action-commit --catalog-action-id <id> --prompt-file tmp/ndf-action-prompt-<id>.md`.
Commander buttons only **copy** the Prompt (not auto-dispatch). After the human pastes
into an Agent, a project `stop` hook may idempotently re-run `action-commit` + snapshot
if the Agent omitted them.

**Live commander** is local `snapshot --serve` at `http://127.0.0.1:8765/`. After the Agent writes `tmp/ndf-canvas-snapshot.json`, that page auto-reloads (`GET /api/events` / `GET /api/refresh`). Do not `curl localhost:8081`. htmlpreview / `docs/ndf-commander.html` is a static backup: rebuild the HTML, then refresh the browser.

Do not treat [`packages/ndf-harness/`](../packages/ndf-harness/) as local process truth.

## Idea button → existing action

| idea button | action_id | Command | Skill / tool |
| ----------- | --------- | ------- | ------------ |
| 生成提案 | `new-proposal` | `/ndf-proposal-generate` | `control-pack --task control_proposal` |
| 审批 Gate | `gate-pipeline` | `/ndf-gate-pipeline` | three gates + [openclaw-delegate.md](../.cursor/skills/ndf-workflow-canvas/openclaw-delegate.md) |
| Design 缺文档 | `design-prepare` | `/ndf-binder-pipeline` | OpenClaw 按 proposal 准备 DESIGN（`--focus-binder-facet design`） |
| 装订 | `binder-pipeline` / `binder-amend` | `/ndf-binder-pipeline` | six facets + openclaw-delegate |
| 晋升 POC | `next-close-hop` + `generate-next-step` | `/ndf-close-hop` | `ndf_close.py plan` / `selected_decision` — not silent promote |
| 委派实现 | `delegate-poc` / `prepare-acp-lease` | `/ndf-poc-delegate` | `pack` + [acp-delegate.md](../.cursor/skills/ndf-workflow-canvas/acp-delegate.md) |
| 运行验证 | `poc-measurement` | `/ndf-poc-measure` | `repair-pack --task poc_measurement` |
| 基线 | `poc-prepare-baseline` | `/ndf-poc-baseline` | `repair-pack --task poc_prepare_baseline` |
| 查看历史 / 详情 | `inspect-ledger` | `/ndf-episode-inspect` | `snapshot --replay-episode` |
| Command Replay（CLI） | — | — | `ndf_replay.py command-replay --episode` |
| 漂移检测 | `diagnose-advisor` | `/ndf-diagnose-drift` | `ndf_advise.py` (read-only) |
| 健康检查 | `run-ndf-control-check` / `diagnose-topic` | `/ndf-diagnose-health` | `spec-health` / `topic-health` |

## Remaining composer / snapshot buttons

| action_id | Command | Skill / tool |
| --------- | ------- | ------------ |
| `align-golden` | `/ndf-golden-align` | `action-begin --operation align-golden` |
| `new-genesis` | `/ndf-genesis` | `genesis-status --json` |
| `submit-process-improvement` / `repair-kernel` | `/ndf-process-improve` | `project-control-pack --task ndf_improvement_proposal` |
| `land-confirm` / `land-review` | `/ndf-process-land` | `project-control-pack --task ndf_improvement_land` |
| `guest-replay-*` (hidden; optional CLI) | `/ndf-guest-replay` | `ndf_replay.py guest-run --adapter vm` |
| `refresh-snapshot` | `/ndf-snapshot-refresh` | `snapshot` (optional `--probe-runtime`) |
| `open-workbench` | `/ndf-workbench-open` | `snapshot --topic` |
| `refresh-topic` | `/ndf-topic-refresh` | `snapshot --topic` |
| `poc-isolation-repair` | `/ndf-poc-isolation` | `repair-pack --task poc_isolation_repair` |

`projection_only` and `openFile` are not Commands.

Idea source (unmodified): [`docs/new_idea.md`](new_idea.md).
