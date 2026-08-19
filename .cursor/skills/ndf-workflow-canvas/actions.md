# Canvas actions

Canvas buttons dispatch `openFile` or `newComposerChat`; they do not run shell directly.
Any action that may change local evidence MUST be wrapped by:

```text
action-begin → operation → action-finish(success|failed, blockers)
→ snapshot --update-embedded <managed-canvas> → atomic replace + verify + projection receipt
```

The Canvas sets local `refresh_in_progress` immediately on dispatch. Bind that local key to
`absorbedActionId` or `payloadSha`, not `snapshotSha`. Only a new `verified_at_generation`
payload clears the safety block.

| Label | Action |
|-------|--------|
| Refresh snapshot | New chat: run official `snapshot --update-embedded <managed-canvas>` and require its verification receipt |
| Refresh topic | New chat: refresh the complete official Canvas projection while retaining topic focus |
| Diagnose topic | New chat: `topic-health --topic <topic> --json`; render structured D/I/T findings and repair routes |
| New Genesis | New chat: create `track=bootstrap` proposal using Genesis templates |
| New Proposal | New chat: classify track and follow `AGENTS.md` proposal gate |
| Open topic | `openFile` for `poc/<topic>/ndf/TOPIC.md` |
| Resolve control next step | Use `health.next_actions[]`; show the concrete OpenClaw task (`legacy_gate_audit`, `gate_sha_audit`, `gate_receipt_draft`, `binder_amend`) |
| Repair with OpenClaw | `control-pack --task <finding.repair_task>` → OpenClaw; then topic-health + refresh |
| Repair with Claude Code | `repair-pack --task poc_isolation_repair|poc_measurement|poc_prepare_baseline` → ACP; then post-checks + refresh |
| Prepare ACP lease | Static preflight passed/runtime not ready: context-verify, full handshake, lease-record, refresh before work |
| Delegate POC | Require verified projection + Context Plan + `static_preflight_passed` + `runtime_dispatch_ready`, then send `acp-delegate.md#poc` |
| Run NDF Control check | `spec-health --json`; render project graph/index/binder/proposal conformance |
| Diagnose with Advisor | Run the relevant read-only `ndf_advise plan --surface graph|bind`; never apply |
| OpenClaw: NDF improvement proposal | `project-control-pack --task ndf_improvement_proposal` → draft process proposal; stop at 已确认 |
| Close plan | New chat: run `ndf_workflow_status.py close-plan --topic <topic> --mode <mode> --json` |
| Delegate promote | New chat: require reviewed promote proposal + close plan, then send promote delegation |
| Open Close Console | Canvas dialog: collect topic/mode/step/instruction; route via [close-console.md](close-console.md) |
| Send close operation | New chat: one legal close step + mandatory `POST_ACTION_SYNC` |
| Refresh dashboard | New chat: full `snapshot --json`, update all Canvas tabs |
| Open R0 Audit instructions | `ndf_replay.py audit --commit <sha> --strict`; no model/tool execution; Composer dispatch is instructions, not completion |
| Open R1 Observation instructions | `ndf_replay.py reconstruct --commit <sha> --level R1`; recorded observations only; Composer dispatch is instructions, not completion |
| R2 Sandbox | `ndf_replay.py sandbox --commit <sha> --episode <id> --profile <profile> --execute`; profile target must bind exact run/role/manifest/plan/env fingerprint/cwd/tool version; recorded completion/cassette/lease must match it, expected outputs must be complete, write roots must be a Context Plan/lease subset, and the profile must confirm cost/side effects |
| R3 Fork | `ndf_replay.py fork --from <sha> --branch <name>`; new counterfactual history |
| Replay diff | `ndf_replay.py diff <left> <right>`; compare manifest/context/events/observations/results/verification separately |
| Replay checkpoint | `ndf_replay.py checkpoint --episode <id> --strategy context-recompile --manifest-sha <sha> --plan-sha <sha> --summary <text>`; current context/gate/repo must re-verify |

## OpenClaw bridge prompt

For topic Control repairs, Composer MUST:

```text
1. Run: python3 spec/meta/tools/ndf_workflow_status.py control-pack --topic <t> --task <task> --episode <id> --json
2. Call MCP openclaw.chat_send with openclaw-delegate.md template + pack JSON
3. Include workspace.repo_root in the message; ask OpenClaw to update `{repo_root}/.openclaw/state.json`
4. Summarize OpenClaw reply: gaps, files touched, next human phrase
5. Record the exact request and response with `message-record --role openclaw`
   under the same Episode (`messages_only` when no tool stream is visible)
6. Re-run `topic-health`, then refresh the official Canvas snapshot
7. Do NOT approve gates or dispatch Claude Code unless user explicitly asks
```

## Claude Code bridge prompt

For normal POC implementation, Composer MUST:

```text
1. Run: python3 spec/meta/tools/ndf_workflow_status.py pack --topic <t> --episode <id> --json
2. Pass pack.workspace.repo_root to Claude Code; worktree MUST be under repo_root
3. Cite `manifest_sha` and the Claude role `context_plan.plan_sha`; run context-verify before work
4. Require run/session/base/repo/worktree/branch/allowed-root handshake; `lease-record`
   must resolve the exact Episode dispatch `pack_sha`
5. Do NOT dispatch unless static and runtime readiness are both true
6. Record completion with changed-file SHAs, git commit, evidence bundle SHA and
   evidence-bound post-check receipts; never synthesize unavailable stream events
```

For bounded repair, use `repair-pack`; an isolation repair MAY run while normal
`pack.safe_to_dispatch=false`, but remains confined to `poc/<topic>/` and MUST NOT
rewrite git history. Measurement repair still requires the implementation gate and a valid perf bind.
`poc_prepare_baseline` copies Trunk comparison code into `poc/<topic>/` after the third
gate (`可以开始实现`); it MUST NOT fill PERF Numbers and is not a page-bottom
「本轮决策 / 生成下一步」 hop.

Every mutating Agent bridge MUST pass the same `episode_id` through pack, runtime lease and
completion evidence. OpenClaw and Claude role plans have different plan SHA values but share
one manifest SHA. Missing platform event streams MUST be reported as coverage gaps, never
backfilled with invented transcript events.

Gate buttons only open a chat asking the human to review. They MUST NOT append an approved
receipt until the human actually sends the exact phrase.

## Close operations

Close buttons MUST use one prompt builder and append:

```text
POST_ACTION_SYNC:
1. Dispatched is not completed.
2. Always append `action-finish` after success or failure.
3. Re-run official canvas-json snapshot and replace all Product/Topics/NDF Control/Agents/Close data.
4. Recompute close steps from evidence.
5. Preserve blockers and pending downstream steps on failure.
6. Verify the operation receipt binds context_plan_sha, source generation, command/input/output
   SHAs and evidence paths; legacy/unbound receipts never complete a step.
```

See [close-console.md](close-console.md). Canvas local history records submissions only and
MUST NOT render fabricated Agent replies.
