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
Command Agent stops after pack JSON; hook sends ACP.

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Require valid implementation gate and complete perf bind skeleton (`vs` / `config_id` / `measure_script`).
3. `repair-pack --topic <t> --task poc_measurement --json`
4. **STOP.** Hook sends Claude Code to write DELTA / PERF numbers with evidence.
5. `binder_amend` cannot clear `unverified_measurement_claim`.
6. Hook closeout refreshes snapshot; do not treat sent alone as success.
