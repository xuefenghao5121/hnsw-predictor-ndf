# POC baseline workflow

Orchestrates `/ndf-poc-baseline`. Catalog id: `poc-prepare-baseline`.

## Command

`/ndf-poc-baseline`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py repair-pack --task poc_prepare_baseline
```

## Delegate

Claude Code via [acp-delegate.md](../acp-delegate.md) bounded POC repair.
**Command Agent builds the pack**, waits for human 「派发」, then runs `dispatch-send`.
Worker copies live under ACP — not in this Composer chat.

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. `action-begin --operation poc_prepare_baseline --catalog-action-id poc-prepare-baseline`
3. `repair-pack --topic <t> --task poc_prepare_baseline --json` (writes `tmp/ndf-dispatch-last-pack.json`)
4. Report pack summary. If not `safe_to_dispatch`: `action-finish cancelled` + `snapshot --out`; stop.
5. If safe: **STOP** for human 「派发」/「继续」.
6. After confirm: `dispatch-send --pack-file tmp/ndf-dispatch-last-pack.json` → Claude Code ACP → closeout.
7. Worker (ACP) copies INTERFACE slice + required Trunk baseline `.h/.cpp` into `poc/<topic>/`.
   MUST NOT measure, MUST NOT amend PERF Numbers/DELTA, MUST NOT touch Trunk `src/`/`include/`/`tests/`.
