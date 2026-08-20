# POC delegate workflow

Orchestrates `/ndf-poc-delegate`. Catalog ids: `delegate-poc`, `prepare-acp-lease`.

## Command

`/ndf-poc-delegate`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py pack --topic <topic> --episode <id> --json
```

Use the catalog `tool=` line for this dispatch.

## Delegate

Claude Code via [acp-delegate.md](../acp-delegate.md) `#poc`.
Command Agent only builds `pack`; hook sends ACP (or lease-only for `prepare-acp-lease`).

## Sequence

1. GIT INPUT checkout of `remote_branch`. Command Agent stays on that branch. Runtime-lease workers MAY use an isolated worktree; that worker branch MUST NOT replace the Command Agent target.
2. `pack --topic <t> --episode <id> --json`. Cite `manifest_sha` and Claude `context_plan.plan_sha`.
3. **STOP.** Hook:
   - `prepare-acp-lease`: lease-record only; refresh snapshot; do not start implementation.
   - `delegate-poc`: require `static_preflight_passed` + `runtime_dispatch_ready` + implement/continue decision + **可以开始实现**, then ACP start.
4. Hook closeout: completion → action-commit → snapshot. Worker markdown is not the command surface.
