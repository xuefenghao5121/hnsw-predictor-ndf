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

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Require valid implementation gate and complete perf bind skeleton (`vs` / `config_id` / `measure_script`).
3. `repair-pack --topic <t> --task poc_measurement --json`
4. Write DELTA / PERF numbers with evidence. Unverified Numbers are the reason to measure, not a blocker.
5. `binder_amend` cannot clear `unverified_measurement_claim`.
6. `action-finish` + snapshot refresh.
