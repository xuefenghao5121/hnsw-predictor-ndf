# POC measure workflow

Orchestrates `/ndf-poc-measure`. Catalog id: `poc-measurement`.

## Command

`/ndf-poc-measure`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py repair-pack --task poc_measurement
```

## Delegate

Claude Code via [acp-delegate.md](../acp-delegate.md) bounded measurement repair.
Command Agent prepares pack, waits for human 「派发」, then runs `dispatch-send`.

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Require valid implementation gate and complete perf bind skeleton (`vs` / `config_id` / `measure_script`).
3. `action-begin` → `repair-pack --topic <t> --task poc_measurement --episode … --action-id … --json`
   (writes `tmp/ndf-dispatch-last-pack.json`).
4. Report pack summary (`safe_to_dispatch` / write root / episode / blockers).
5. If not safe: `action-finish cancelled` + `snapshot --out --topic`; stop.
6. If safe: **STOP** for human 「派发」/「继续」 in the same chat.
7. After human confirms: `dispatch-send --pack-file tmp/ndf-dispatch-last-pack.json …`
   (sends Claude Code ACP; waits; completion → action-commit → action-finish → snapshot).
8. `binder_amend` cannot clear `unverified_measurement_claim`.
9. Do not treat transport `sent` alone as success.
