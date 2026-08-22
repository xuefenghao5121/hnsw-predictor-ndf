# Binder pipeline workflow

Orchestrates `/ndf-binder-pipeline`. Catalog ids: `design-prepare`,
`binder-pipeline`, `binder-amend`. Six facets stay six facets.
`design-prepare` uses `--focus-binder-facet design`; distinguish by
`catalog_action_id` in the copied Prompt.

## Command

`/ndf-binder-pipeline`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py control-pack --topic <topic> --task binder_pipeline --json
python3 spec/meta/tools/ndf_workflow_status.py control-pack --topic <topic> --task binder_amend --json
```

Use the catalog `tool=` line for this dispatch.

## Delegate

OpenClaw via [openclaw-delegate.md](../openclaw-delegate.md) pipeline B (面).
Facets: TOPIC → DESIGN → PERF_BASELINE → DELTA → INTERFACE → COMMITS.
`binder_amend` is same-hypothesis facet tweak only (`--focus-binder-facet`).
Command Agent prepares pack, waits for human 「派发」, then `dispatch-send`.

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Prefer `--resume` when binder Episode is active.
3. `control-pack` then report summary; wait for 「派发」; then `dispatch-send` (not Agent `chat_send`).
4. Worker amends only the focused facet; complete facets are recheck no-ops.
5. MUST NOT write gate approvals, PERF Numbers, DELTA Rounds, or evidence.
6. Hypothesis change is `new_poc` via `/ndf-proposal-generate`, not amend.
7. Hook closeout refreshes snapshot.
