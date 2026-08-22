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
Command Agent builds `pack`, waits for human 「派发」, then `dispatch-send`
(or lease-only for `prepare-acp-lease`).

## Sequence

1. GIT INPUT checkout of `remote_branch`. Command Agent stays on that branch. Runtime-lease workers MAY use an isolated worktree; that worker branch MUST NOT replace the Command Agent target.
2. `pack --topic <t> --episode <id> --json`. Cite `manifest_sha` and Claude `context_plan.plan_sha`.
3. Report summary; wait for 「派发」; then `dispatch-send`:
   - `prepare-acp-lease`: lease-record only; refresh snapshot; do not start implementation.
     After `git worktree add`, tooling auto-symlinks gitignored local deps from the
     main repo (`hnswlib`, `output`, ignored `data/*` artifacts) into the lease
     worktree and ensures `build/` + `results/` exist — see
     [acp-delegate.md](../acp-delegate.md) Runtime lease handshake.
   - `delegate-poc`: require `static_preflight_passed` + **active isolated lease** + implement/continue decision + **可以开始实现**, then ACP start.
4. Closeout: completion → action-commit → action-finish → snapshot. Worker markdown is not the command surface.
