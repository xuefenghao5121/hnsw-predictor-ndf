# Canvas actions

Canvas buttons dispatch `openFile` or `newComposerChat`; they do not run shell directly.
Any action that may change local evidence MUST be wrapped by:

```text
action-begin → operation → action-finish(success|failed, blockers)
→ snapshot --update-embedded <managed-canvas> → atomic replace + verify + projection receipt
```

The Canvas sets local `refresh_in_progress` immediately on dispatch. Bind that local key to
`absorbedActionId` or `payloadSha`, not `snapshotSha`. Only a new `fresh`
payload clears the safety block.

| Label | Action |
|-------|--------|
| Refresh snapshot | Header only. Official `snapshot --update-embedded <managed-canvas> --probe-runtime --topic <business-topic>`; require verification receipt. Unchanged Merkle layers MUST NOT re-run graphcheck. |
| 打开工作台 | Topics, when selector ≠ `focusedTopicId`. `snapshot --update-embedded <managed-canvas> --topic <id>` (no `--probe-runtime`); isomorphic to Replay 「查这条账」 |
| Refresh topic | Same snapshot builder with `--topic <id>` (no `--probe-runtime`). Lives in Topics 阻塞与修复 header |
| Diagnose topic | `spec-health --json` then `topic-health --topic <topic> --json`; render in 阻塞与修复 including ndf_graphcheck; do not repair. Next hop: route each finding to its **space card** (Design / Implementation / Test) or page-bottom **本轮决策与实现委派** — not「去阻塞与修复点修复钮」. Decision composer reads **focusedTopic workbench** only |
| New Genesis | **NDF Control only.** `genesis-status --json`; draft `spec/open/proposal-project-genesis.md` track=bootstrap; stop at IDEA已审核. Disabled when Genesis is already accepted. Never shown on Product |
| New Proposal | Product idea entry; no existing topic required. Empty text MUST NOT dispatch and MUST NOT let the Agent invent an idea. Write the exact utterance to gitignored `tmp/ndf-product-intent-<action_id>.md`; wrap it as `BEGIN HUMAN PRODUCT INTENT` (intent field, not the Agent main instruction). `control-pack --task control_proposal --intent-file <tmp-file>` with **no** `--topic`. OpenClaw MUST web-search related work (not local files only), then draft one `spec/open/proposal-*.md` (`Status: Pending confirmation`); uncertain track → poc. MUST NOT create `poc/` before 已确认. Process stays on Control 提交流程改进 — MUST NOT write `spec/meta/open/` from this Product entry. Enabled only when projection is `fresh` **and** Golden is `aligned` or `docs_only_ahead` **and** trim(intent) is non-empty. Missing / unresolvable / `head_ahead_of_golden` keep it disabled; use Align Golden. |
| Align Golden | **Product only.** Enabled when projection is `fresh` and Golden is not SHA-`aligned`. Composer: `action-begin --operation align-golden`; `git diff --name-only <golden> HEAD -- src include tests`. Trunk source changed → Claude Code re-run Golden matrix, write `baselines/bl-trunk-golden-<head>.md`, update `golden-baseline.md`. Docs/process/poc only → do not re-run; after refresh `docs_only_ahead` unblocks New Proposal. Open Golden is read-only. |
| Open topic | `openFile` for `poc/<topic>/ndf/TOPIC.md` from TOPIC 总览 |
| Repair with OpenClaw | Design space card only: `control-pack --task gate_pipeline|binder_pipeline|binder_amend|<finding.repair_task>` → actual MCP send → request/response receipt → topic-health + refresh; blocked paths show retry. 阻塞与修复 does not repeat these buttons |
| Repair with Claude Code | Implementation space card: `repair-pack --task poc_prepare_baseline` **when** gap `missing_baseline_workspace` exists（INTERFACE + 拷贝 Trunk 对照代码 into `poc/<topic>/`，形成可测基线）。Test space card: `repair-pack --task poc_measurement` **when** baseline is ready and gap `numbers_pending` exists（R0 对齐金标）。Implementation space card: `poc_isolation_repair` **only when a matching finding exists**. After withdraw with missing baseline: command order is Implementation 基线准备 → page-bottom **本轮决策与实现委派** → Delegate POC; Test measure becomes available after baseline prepared. 阻塞与修复 does not repeat these buttons |
| Human POC decision | Topics **page-bottom 本轮决策与实现委派** only (fields from **focusedTopic**, not directory row): offered prefill chips + TextArea + **生成下一步** (writes `selected_decision` hop only; does not delegate implementation). Implementation space card shows at most a pointer to page-bottom — **no** composer. Same card lower section is the sole Delegate POC / Prepare ACP lease entry. Close modes record `selected_decision` then run the first legal close hop in the same chat. After 已审核, continue the close-apply chain here. Topics recovery button only if the human left or ACP/blocker stopped the chain. No Close tab. Hypothesis fork is `new_poc`. Empty text must not dispatch or default to continue_exploring. **Early close**: when gates are not all `valid` (`decision.state=not_ready`, exploring/blocked), still show the page-bottom composer; offered routes are reject (+ amend/new_poc). Promote/partial/implement stay blocked as `gates_not_valid` |
| Next close hop | Topics recovery after close `selected_decision` on the **本轮决策与实现委派** card. Label reject N/A 「继续关闭收口」. `closeApplyChainPrompt` from `nextStep` unless ACP integrate is required |
| Prepare ACP lease | **本轮决策与实现委派 module only** (not on space cards). Enabled only when static preflight passed/runtime not ready: context-verify, full handshake, lease-record against a statically-ready pack, then snapshot refresh; do not start implementation |
| Delegate POC | **本轮决策与实现委派 module only** (not on space cards). Enabled only with verified projection + Context Plan + `static_preflight_passed` (including graphcheck) + `runtime_dispatch_ready` **and** `selected_decision` implement/continue_exploring. Send `acp-delegate.md#poc`, then mandatory `POST_DISPATCH_SYNC`. Worker markdown is not the command surface |
| Run NDF Control check | `spec-health --json`; render meta/product graph, index, binder and proposal-plane as **plane-routed** findings. When Topics has no exploring/blocked POC, `binder_health` is `not_applicable` (Trunk); do not refresh closed binders or treat that as a process proposal. Do not treat product/binder failures as process proposals |
| Diagnose with Advisor | First `spec-health --json`, then read-only `ndf_advise plan`; never apply; never recommend copying product clauses or POC binder fields into `spec/meta/`. If binder_health is n/a, do not route to Topics |
| OpenClaw: 修内核 | Finding-driven only: `project-control-pack --task ndf_improvement_proposal --origin health_finding --episode <id>`; requires current spec-health findings; draft one `spec/meta/open/` process proposal and stop at 已确认. Binder → Topics only when an active POC exists; product graph → Product |
| 提交流程改进 | Human-intent entry, always visible in 工作流演进. Write exact input to a gitignored `tmp/` intent artifact; run `project-control-pack --task ndf_improvement_proposal --origin human_intent --intent-file <tmp-file> --episode <id>`; require intent SHA + verified context, call `openclaw.chat_send`, record request/response, stamp `Status: Pending confirmation`, action-finish and refresh. Never write stable META, product/POC docs, or `.openclaw/state.json`. Next Canvas action is 推进 |
| 推进：已确认 / 推进：已审核 | Focused process hop CTA in 工作流演进 when `processHop` exists. `project-control-pack --task ndf_improvement_land --proposal <path> --episode <id>`; actual `openclaw.chat_send`; wait for the exact human phrase. Confirm hop lands `spec/meta/` then waits for 已审核 in the same chat if the human stays; review hop only marks the proposal reviewed. Button click is not approval. Catalog stays read-only (no Open md row buttons) |
| 去 Topics / 去 Product | Control plane handoff only (`plane-tab`). Does not write `spec/meta/` |
| 沙箱回放这次 hop | Host launcher only: `guest-run --adapter vm` (local KVM image; Cube optional). Proof is `ndf-replay-guest-proof/v1` (`valid=true`, contract `adapter=vm`). Forbid host-mount of live checkout. No KVM/image → `environment_blocked`, no soft fallback |
| 沙箱回放到上一步 | Same guest-run; report only the selected timeline prefix |
| Open R0 Audit (CLI) | `ndf_replay.py audit --commit <sha> --strict`; no model/tool execution |
| Open R1 Observation (CLI) | `ndf_replay.py reconstruct --commit <sha> --level R1`; recorded observations only |
| R2 Sandbox (CLI) | `ndf_replay.py sandbox --commit <sha> --episode <id> --profile <profile> --execute`; adapter `bwrap` or `vm`; not Canvas completed-replay |
| Guest VM replay (Canvas) | `ndf_replay.py guest-run --commit <sha> --episode <id> --adapter vm`. First-time image: `ndf_replay.py guest-image`. Proof `ndf-replay-guest-proof/v1` with `adapter=vm`. MUST NOT host-mount live `repo_root` |
| R3 Fork (CLI only) | `ndf_replay.py fork --from <sha> --branch <name>`; MUST NOT appear on Canvas Replay |
| Replay diff (CLI) | `ndf_replay.py diff <left> <right>`; not on Canvas Replay |
| Replay checkpoint | `ndf_replay.py checkpoint --episode <id> --strategy context-recompile --manifest-sha <sha> --plan-sha <sha> --summary <text>`; current context/gate/repo must re-verify |

## OpenClaw bridge prompt

For topic Control repairs, Composer MUST:

```text
1. Run control-pack; create/preserve request_id; record control-dispatch `requested`
2. Record ndf-agent-message/v1 request; record `sent`
3. ACTUALLY call MCP openclaw.chat_send with openclaw-delegate.md template + pack JSON
4. Record exact response; record `acknowledged` (and `waiting_human` for gate)
5. Include workspace.repo_root; OpenClaw updates `{repo_root}/.openclaw/state.json`
6. On any failure record `blocked` + blocker and offer retry
7. Re-run `topic-health`, refresh official Canvas snapshot, and show dispatch state
8. Do NOT approve gates or dispatch Claude Code unless user explicitly asks
9. Gate may write only `GATES.md`; on a missing binder facet record
   `blocked_by_binder + next_binder_facet` and hand off. It MUST NOT create binder files.
10. Binder may write only its focused facet; a complete facet is audit/recheck no-op.
    It MUST NOT write gate approvals or select close.
11. Binder steps declare `changed_sections`; OpenClaw may edit contract/skeleton slices
    but MUST NOT edit PERF Numbers, DELTA Rounds or evidence. Measurement sections require
    a Claude Code completion joined to run/lease/measure evidence.
```

Three valid gates MUST display `decision_required`, not automatic close. Close hops
MUST require a structured human `decision.selected` plus the branch proposal and
bound close evidence; negative prose in DESIGN/GATES/NOTES is never a decision.
**生成下一步** close hops MUST record `selected_decision` then run the first legal
close hop in the same chat. After 已审核, continue the close-apply chain in that
chat; do not bounce to Topics for mechanical hops.
There is no Close tab. Hypothesis change MUST draft `spec/open/proposal-*.md`
(`track=poc`) and a sibling topic with `depends_on_topics`; MUST NOT `binder_amend`
the current `active_hypothesis`. `amend` is same-hypothesis binder/contract tweak only.
Gate UI MUST show `bundle_mode` and review slice IDs. `legacy_whole_file` receipts never
match `review_slice`; mutable Numbers/Rounds/evidence/COMMITS/GATES changes do not alter
review-slice SHA.

## Claude Code bridge prompt

For normal POC implementation, Composer MUST:

```text
1. Run: python3 spec/meta/tools/ndf_workflow_status.py pack --topic <t> --episode <id> --json
2. Pass pack.workspace.repo_root to Claude Code; worktree MUST be under repo_root
3. Cite `manifest_sha` and the Claude role `context_plan.plan_sha`; run context-verify before work
   and trust `valid` (content SHA). Manifest-only inequality is not a stop.
4. Require run/session/base/repo/worktree/branch/allowed-root handshake; `lease-record`
   may resolve a statically-ready (`safe_to_delegate` / `static_preflight_passed`) dispatch pack,
   not only `safe_to_dispatch=true`
5. Do NOT start implementation writes unless static and runtime readiness are both true
6. Record completion with changed-file SHAs, `changed_sections`, git commit, evidence bundle SHA and
   evidence-bound post-check receipts; never synthesize unavailable stream events
7. Run `POST_DISPATCH_SYNC` below. Do not leave the user in the Claude Code chat as the commander.
```

`POST_DISPATCH_SYNC` (Claude Code write runs; markdown is never close):

```text
1. completion-record --file <completion.json> --episode <id> --role claude-code --coverage …
2. If a same-topic lease is still active: lease-record --result released with the same binding
3. topic-health --topic <t> --json
4. snapshot --update-embedded <managed-canvas> --json (updated=true). Do not pass --probe-runtime.
5. Report only the next Canvas action from findings / decision_required / Topics close hop
```

For bounded repair, use `repair-pack`; an isolation repair MAY run while normal
`pack.safe_to_dispatch=false`, but remains confined to `poc/<topic>/` and MUST NOT
rewrite git history. Measurement repair requires a valid implementation gate and a complete
perf bind skeleton (`vs` / `config_id` / `measure_script`). Unverified or pending Numbers
are the reason to measure, not a blocker. `binder_amend` cannot clear
`unverified_measurement_claim`.

Every mutating Agent bridge MUST pass the same `episode_id` through pack, runtime lease and
completion evidence. OpenClaw and Claude role plans have different plan SHA values but share
one manifest SHA. Missing platform event streams MUST be reported as coverage gaps, never
backfilled with invented transcript events.

Gate buttons only open a chat asking the human to review. They MUST NOT append an approved
receipt until the human actually sends the exact phrase.

## Close hops

Close buttons live on Topics. They MUST use `closeOperationPrompt` and the hop contract
in [close-console.md](close-console.md). Replace Product/Topics/NDF Control/Agents/Replay
on refresh. There is no Close tab.
