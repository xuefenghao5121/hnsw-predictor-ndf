# Diagnose health workflow

Orchestrates `/ndf-diagnose-health`. Catalog ids: `run-ndf-control-check`, `diagnose-topic`.
Read-only. Do not repair.

## Command

`/ndf-diagnose-health`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py spec-health --json
python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic <topic> --json
```

Use the catalog `tool=` line for this dispatch.

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Control: `spec-health --json`; render plane-routed findings (meta/product graph, index, binder, proposal-plane).
3. Topics: `spec-health --json` then `topic-health --topic <topic> --json` including ndf_graphcheck.
4. Route each finding to its space card or page-bottom decision — not a extra 「去阻塞与修复」 repair row.
5. When no exploring/blocked POC, `binder_health` is `not_applicable`. Do not treat product/binder failures as process proposals.
