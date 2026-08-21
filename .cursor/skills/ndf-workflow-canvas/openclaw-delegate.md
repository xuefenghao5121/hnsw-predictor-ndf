# OpenClaw Control delegation

Canvas Control actions delegate NDF document-flow work to the configured OpenClaw
conductor session. Read `session_key` from `AGENTS.md`; never hardcode.
Gateway reachable ≠ session dispatchable: the key MUST appear in
`openclaw sessions` (or be a UUID). Routing keys (feishu `agent:…:…`) stay valid;
`dispatch-send` uses gateway `sessionKey`, not `agent --session-id`. If pack
blockers include `openclaw_session_invalid` / `openclaw_session_unconfigured`,
fix `AGENTS.md` then refresh probe — Canvas MUST NOT write `AGENTS.md`.

## Two pipelines (hard split)

| Pipeline | Name | Steps | Truth | Human pause |
|----------|------|-------|-------|-------------|
| A | **闸 / gate** only | 3: TOPIC已审核 → DESIGN已审核 → 可以开始实现 | `GATES.md` | Every gate phrase |
| B | **面 / binder facet** (never call 闸) | 6: TOPIC → DESIGN → PERF → DELTA → INTERFACE → COMMITS | binder files | Usually none; recheck topic-health |

- Main Canvas buttons: `gate_pipeline` / `binder_pipeline` (one Cursor dispatch each).
- Step buttons resume the **same** pipeline Episode (`--resume` / active binding).
- MUST NOT merge A+B into one unlabeled mega-dispatch.
- MUST NOT forge `approved_by`.
- Gate owns only `GATES.md`; binder owns its focused facet. A missing facet is a
  structured handoff, never permission for gate to create binder documents.
- Gate receipts MUST copy `bundle_mode` and `slice_manifest_sha` when **writing a new
  receipt**. A `legacy_whole_file` receipt never validates a `review_slice` bundle.
- Existing receipts stay valid when `expected_content_sha` matches, even if
  `slice_manifest_sha` differs (line-number shift or semantic-manifest migration).
  Trust `context-verify.valid` and topic-health `state=valid` / `sha_aligned`; do not
  treat manifest-only inequality as a stop.

## Bridge sequence (Composer → dispatch-send)

```text
0. EXECUTE now. Do not explain/return this template or stop after newComposerChat.
1. Prefer resume: control-pack --topic <t> --task <task> --episode <active> --resume [--focus-gate|--focus-binder-facet] --json
   Else: control-pack --topic <t> --task gate_pipeline|binder_pipeline|… --episode <new> --json
2. Command Agent reports pack summary (written to tmp/ndf-dispatch-last-pack.json).
   MUST NOT call openclaw.chat_send from Composer.
3. If not safe_to_dispatch: action-finish cancelled + snapshot --out; stop.
4. If safe: STOP for human 「派发」/「继续」 in this chat.
5. After confirm: dispatch-send --pack-file tmp/ndf-dispatch-last-pack.json
   (sends via OpenClaw CLI/gateway, waits for ndf-dispatch-notify/v1, reads
   pack.completion_receipt_path from disk, then completion-record →
   action-commit → action-finish → snapshot).
6. Gate: record waiting_human when next_human_phrase returns. Binder: continue only POC NDF /
   workflow preparation. Never dispatch Claude Code here.
7. Success requires disk ndf-agent-completion/v1 + succeeded closeout; Composer
   creation / sent / stdout JSON alone is never success. Stop hook skips ready packs awaiting human dispatch.
```

## Workspace binding (all tasks)

Every control-pack carries:

```json
"workspace": {
  "repo_root": "/absolute/path/to/repo",
  "repo_name": "hnsw-predictor-ndf",
  "repo_head": "git-sha",
  "active_topic": "bfs-cluster",
  "topic_dir": "poc/bfs-cluster/",
  "topic_ndf_dir": "poc/bfs-cluster/ndf/"
}
```

OpenClaw MUST on receive:

1. Read `{workspace.repo_root}/.openclaw/state.json` if it exists.
2. Compare `workspace.repo_root` / `repo_head` with the pack; if drifted, note in reply.
3. Write/update `{repo_root}/.openclaw/state.json` → `workspace` and `active_topic` before touching files.
4. Resolve all relative paths under `workspace.repo_root` (never assume process cwd).
5. If `repo_root` differs from prior binding, switch project and tell the user.
6. Verify the exact Manifest + OpenClaw role plan SHA before work and obey its ordered reads,
   graph slice and privileges. A Claude-role plan shown in Canvas is human preview only;
   derive the OpenClaw plan from the shared manifest via control-pack.

Do not use global `~/.openclaw/agents/...` as project state.

## gate_pipeline

```text
【track=poc】【control=gate_pipeline】topic: <topic>
pipeline: gate
session_key: <from control-pack>
gates_ordered: topic_review → design_review → implementation_approval
wait_human_phrase_per_gate: true

You are OpenClaw. Stay in this session until all needed gates are audited/drafted.
For EACH gate in order:
  1. Record gate.audit (pipeline-step-record).
  2. MAY draft GATES.md pending/invalidated rows; MUST NOT set approved_by.
     Pending rows MUST leave `approved_content_sha` empty; show the candidate
     `expected_content_sha` only in the audit note.
  3. Record gate.draft with changed_files evidence if GATES.md changed.
  4. If the bound bundle lacks a binder facet, STOP with:
     blocked_by_binder=true, blocked_gate=<gate>, next_binder_facet=<facet>.
     Record control.handoff. MUST NOT create or amend TOPIC/DESIGN/PERF_BASELINE/
     DELTA/INTERFACE/COMMITS.
  5. Otherwise STOP and return exact next_human_phrase for that gate.
  6. After human sends the phrase, copy the current control-pack
     `gates.<gate>.expected_content_sha` verbatim into `approved_content_sha`, then
     also copy `bundle_mode` and `slice_manifest_sha`, then
     record gate.confirmed with human actor (or tell Composer to).
     NEVER use raw `sha256sum <file>`: canonical bundle SHA hashes sorted
     repo-relative path + NUL + bytes + NUL and intentionally differs from file SHA.
  7. Re-run topic-health and require `sha_aligned=true` (content SHA + review_slice
     mode; unequal slice_manifest_sha alone is not a mismatch). Content SHA mismatch
     means the receipt was not approved and MUST NOT advance.
All gates valid means decision_required; it does NOT select implement/promote/reject/close.
Do not jump to binder_pipeline. Do not blur three gates into one completion event.
```

## binder_pipeline

```text
【track=poc】【control=binder_pipeline】topic: <topic>
pipeline: binder
session_key: <from control-pack>
facets_ordered: topic → design → perf_baseline → delta → interface → commits

You are OpenClaw. Stay in this session until missing binder facets are amended.
For EACH needed facet in order:
  1. Record binder.audit.
  2. If already complete, do not rewrite it; record no-op binder.recheck.
  3. Otherwise amend only that facet under poc/<topic>/ndf/; record binder.amend
     with exact changed_files + changed_sections evidence.
  4. Recheck (topic-health / bindcheck as needed); record binder.recheck.
Do not call these 面 “闸”. Do not approve human gates, write GATES.md, select a
close mode, or merge with gate_pipeline.
Binder/OpenClaw MUST NOT write `perf_numbers`, `delta_rounds`, evidence or measurement
claims. Those require Claude Code run/lease/completion + measure/evidence receipts.
`unverified_measurement_claim` is not a binder facet; do not treat it as `binder_amend`.

## Gate review slices

- `topic_review`: `topic_contract` (+ proposal contract).
- `design_review`: topic + `design_contract`.
- `implementation_approval`: topic + design + `perf_bind` +
  `delta_hypothesis` + `interface_contract`.
- Mutable outside gate SHA: topic runtime/baseline headers, PERF Numbers,
  DELTA Rounds, evidence, COMMITS, GATES.
- Missing/duplicate/mismatched/nested markers fail closed.
```

## Episode resume / stale pack

- Prefer `--resume` when `control_pipelines.<pipe>.resume === true`.
- If `force_new_episode === true` (or blockers contain `episode_manifest_mismatch` /
  `control_pack_resume_failed` / `context_plan_sha_drift` / `request_id identity mismatch`):
  **MUST** mint a new `episode_id` **without** `--resume`, and a **new** `request_id`.
  Do not finish closed solely because an old Episode cannot rebind.
- `topic_review` SHA mismatch / `invalidated` is expected work for `gate_sha_audit` /
  gate-pipeline focus — it is **not** a reason to skip `openclaw.chat_send`.

## legacy_gate_audit (step focus / resume)

按闸序：`门禁 1/3 · TOPIC已审核` → `2/3 · DESIGN已审核` → `3/3 · 可以开始实现`。
Prefer `--resume` when `control_pipelines.gate.active_episode_id` exists.

```text
【track=poc】【control=legacy_gate_audit】topic: <topic>
gate: <topic_review|design_review|implementation_approval>
session_key: <from control-pack>

Audit ONE ordered legacy POC gate. MAY draft pending GATES.md. MUST NOT approve.
Return next human phrase for the focused gate. Record gate.audit[/draft] on the Episode.
```

## gate_sha_audit

```text
【track=poc】【control=gate_sha_audit】topic: <topic>
session_key: <from control-pack>

Compare each gate receipt in GATES.md against canonical bundle SHA from control-pack.
Report valid / missing / legacy_unknown / invalidated per gate.
Do not append approved receipts. Return next_human_phrase if a gate is ready for human review.
```

## gate_receipt_draft

```text
【track=poc】【control=gate_receipt_draft】topic: <topic>
session_key: <from control-pack>

Prepare the next pending gate bundle summary for human review.
List bundle paths, content SHA, and the exact phrase the human must send.
Do not write approved_by. Return the phrase prominently.
```

## binder_amend (facet focus / resume)

Prefer `--resume` + `--focus-binder-facet` when binder Episode is active.

```text
【track=poc】【control=binder_amend】topic: <topic>
binder_facet: <topic|design|perf_baseline|delta|interface|commits>
session_key: <from control-pack>

Revise only the focused binder facet under poc/<topic>/ndf/.
Record binder.audit → binder.amend → binder.recheck. Gates remain human-approved.
```

## control_proposal

Topic-bound (existing POC / close-revise):

```text
python3 spec/meta/tools/ndf_workflow_status.py control-pack \
  --topic <topic> --task control_proposal --episode <episode-id> --json
```

```text
【track=process|poc】【control=control_proposal】topic: <topic>
session_key: <from control-pack>

Draft or revise spec/open/ or spec/meta/open/ proposal per AGENTS.md track routing.
Do not land stable clauses without 已确认/已审核. Return proposal path and next step.
```

Product idea hop (no topic yet; Canvas New Proposal):

```text
python3 spec/meta/tools/ndf_workflow_status.py control-pack \
  --task control_proposal --intent-file tmp/ndf-product-intent-<action_id>.md \
  --episode <episode-id> --json
```

OpenClaw MUST research locally (Charter / current contracts / existing `spec/open/`)
**and** actually web-search related papers, systems, and public surveys. Cite sources.
Web numbers are not new SLAs. Draft exactly one `spec/open/proposal-*.md` with
`Status: Pending confirmation`. Stop at 已确认. MUST NOT invent `--topic`, MUST NOT
create `poc/`, and MUST NOT write `spec/meta/open/` from this Product entry.


## Project NDF improvement proposal

Finding-driven repair:

```text
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack \
  --task ndf_improvement_proposal --origin health_finding \
  --episode <episode-id> --json
```

Human-initiated workflow evolution:

```text
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack \
  --task ndf_improvement_proposal --origin human_intent \
  --intent-file tmp/ndf-process-intent-<action-id>.md \
  --episode <episode-id> --json
```

The first form requires current META health findings. The second requires a
non-empty human intent, `intent_sha`, explicit Episode and valid Context Plan;
it MUST NOT require health findings. In both cases Cursor MUST actually call
`openclaw.chat_send`, record exact request/response in that Episode, finish the
Canvas action and refresh the snapshot.

OpenClaw drafts one focused `track=process` proposal under `spec/meta/open/`
with `Status: Pending confirmation` and stops. Canvas then shows **推进：已确认**.
MUST NOT copy product clauses, SLA numbers, or POC binder fields into `spec/meta/`.
MUST NOT modify stable META or `.openclaw/state.json` on the draft hop.

## Process proposal land / review

```text
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack \
  --task ndf_improvement_land --proposal spec/meta/open/proposal-meta-<id>.md \
  --episode <episode-id> --json
```

Cursor MUST actually call `openclaw.chat_send`, then wait for the exact human
phrase. `waiting_confirm` + 「已确认」lands pack-allowed `spec/meta/` roots and
sets `Status: Implemented on YYYY-MM-DD`. `waiting_review` + 「已审核」only
marks the proposal reviewed. Button click is not approval.
Binder instance failures go to Topics; product graph failures go to Product.

## Decision / Close boundary

- `gate.confirmed` and `decision.selected` are distinct human events.
- Three valid gates project `decision_required`; never infer reject from DESIGN,
  DELTA, GATES or NOTES prose.
- Canvas shows a **decision briefing** (latest round verdict, worker summary,
  Decision path, openFile to markdown). The human writes the next decision in
  natural language. Suggested paths only prefill that text.
- **生成下一步** maps the human text to one legal route:
  `implement`, `continue_exploring`, `amend`, `promote`, `partial`, `reject`,
  `new_poc`. If ambiguous, ask; do not default to `continue_exploring`.
- The third gate `可以开始实现` is permission to write POC code, not a decision.
- `implement` vs `continue_exploring` remain mutually exclusive after mapping:
  first realization of the approved DESIGN vs another DELTA round on a frozen
  contract.
- `amend` is same-`active_hypothesis` binder/contract tweak plus re-gate only.
  Changing the hypothesis / 换方向 / 重写 TOPIC 假设 maps to `new_poc`, never
  `amend`. Do not record `selected_decision` on the current topic for `new_poc`.
- Record `decision.selected` with actor=human only for current-topic modes
  (`implement|continue_exploring|amend|promote|partial|reject`). The payload MAY
  include `human_text`. The event MUST NOT claim file mutations.
- OpenClaw then amends only the TOPIC.md **runtime header**
  `> selected_decision: <decision>` (`changed_sections=topic_runtime_headers`).
  MUST NOT edit `topic_contract` or the contract-slice `open_decision`, PERF
  Numbers, DELTA Rounds, evidence, or GATES.md.
- Execute the mapped hop with real tools:
  `implement`/`continue_exploring` → Delegate POC;
  `amend` → same-hypothesis binder;
  `promote`/`partial`/`reject` → record `selected_decision`, then first legal close
  hop in the same chat (`control_proposal` if unreviewed, else the close-apply
  chain). After 已审核 continue plan/graph/finalize here; Topics is recovery
  only. There is no Close tab;
  `new_poc` → draft `spec/open/proposal-*.md` `track=poc` for a sibling topic
  with `depends_on_topics` including the current topic; stop at 已确认.
- A close branch requires the explicit decision plus its reviewed proposal and
  bound close-plan/verification receipts. Historical negative rounds remain evidence.

## Write boundary (all tasks)

| Allowed | Forbidden |
|---------|-----------|
| `poc/<topic>/ndf/` | `src/`, `include/`, `tests/` |
| `spec/open/`, `spec/meta/open/` | `spec/meta/` stable body |
| `.openclaw/state.json` | Silent `GATES.md` approval |
| pipeline-step-record events | Cross-pipeline unlabeled merge |
