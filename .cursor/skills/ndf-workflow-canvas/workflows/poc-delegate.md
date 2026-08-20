# POC delegate workflow

Orchestrates `/ndf-poc-delegate`. Catalog ids: `delegate-poc`, `prepare-acp-lease`.

## Command

`/ndf-poc-delegate`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py pack --topic <topic> --episode <id> --json
python3 spec/meta/tools/ndf_workflow_status.py lease-record --file tmp/lease.json --episode <id> --json
```

Use the catalog `tool=` line for this dispatch.

## Delegate

Claude Code via [acp-delegate.md](../acp-delegate.md) `#poc`.

## Sequence

1. GIT INPUT checkout of `remote_branch`. Command Agent stays on that branch. Runtime-lease workers MAY use an isolated worktree; that worker branch MUST NOT replace the Command Agent target.
2. `pack --topic <t> --episode <id> --json`. Cite `manifest_sha` and Claude `context_plan.plan_sha`; `context-verify`.
3. If static preflight passed and runtime not ready: `lease-record` only; refresh snapshot; do not start implementation (`prepare-acp-lease`).
4. If `static_preflight_passed` and `runtime_dispatch_ready` and `selected_decision` is implement/continue_exploring: wait for **可以开始实现**, then acp-delegate `#poc`.
5. POST_DISPATCH_SYNC: completion-record, lease release if active, topic-health, snapshot (no `--probe-runtime`).
6. Worker markdown is not the command surface.
