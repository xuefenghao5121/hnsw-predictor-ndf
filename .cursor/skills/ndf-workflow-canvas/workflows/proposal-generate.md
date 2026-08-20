# Proposal generate workflow

Orchestrates `/ndf-proposal-generate`. Closed catalog id: `new-proposal`.
Enablement stays in `action-registry.json`; this skill does not invent Golden/gate/freshness.

## Command

`/ndf-proposal-generate`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_workflow_status.py control-pack --task control_proposal --intent-file <tmp-file> --json
```

## Delegate

OpenClaw via [openclaw-delegate.md](../openclaw-delegate.md) `control_proposal`
(Product idea hop: no `--topic`).

## Sequence

1. Honor NDF GIT INPUT: fetch/checkout/pull the existing `remote_branch`. Do not create a replacement feature branch.
2. `action-begin --operation control_proposal`
3. Write exact human utterance to `tmp/ndf-product-intent-<action_id>.md` wrapped as `BEGIN HUMAN PRODUCT INTENT`.
4. Run the unique CLI. Empty intent MUST NOT dispatch.
5. Actual `openclaw.chat_send`. Web-search related work; draft one `spec/open/proposal-*.md` (`Status: Pending confirmation`).
6. Stop at **已确认**. MUST NOT create `poc/` before that phrase. MUST NOT write `spec/meta/open/`.
7. `action-finish` then `snapshot --out tmp/ndf-canvas-snapshot.json` and `python3 spec/meta/cockpit/build_standalone.py`.

Human phrase remains **已确认**, not 同意/ok.
