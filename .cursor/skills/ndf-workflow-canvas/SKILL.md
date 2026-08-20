---
name: ndf-workflow-canvas
description: >-
  Projects the local business project into the NDF commander (React+D3) with
  five tabs (Product / Topics / NDF Control / Agents / Replay). Cursor Canvas
  is retired from the visualization chain. Close is a Topics hop sequence, not a tab. Every control
  is a closed NDF action-registry id. Use when the user asks for an NDF workflow
  canvas, commander, product cockpit, Genesis, POC workbench, governance health,
  agent runtime, sandbox delegation, or close visualization.
disable-model-invocation: true
---

# NDF Workflow Commander

## Authority

Read in this order:

1. `AGENTS.md`
2. `spec/meta/README.md`
3. `spec/meta/language.md` — [[META-008]]
4. `spec/meta/process.md` — [[META-009]]…[[META-015]], [[BEH-025]]
5. `spec/meta/tools/README.md`

Never use `packages/ndf-harness/` or `.cursor/skills/ndf-harness/` as local
process truth. Business truth comes from `spec/00–50` + Trunk; Meta controls flow.
The only derived cockpit is the React+D3 NDF commander (`spec/meta/cockpit/`).
Do not create, refresh, or link a Cursor Canvas. Every control is an id in
`spec/meta/cockpit/action-registry.json`. UI MUST NOT invent hops.

## Open or refresh

**Agent 纪律**：Command Agent MUST NOT 启动或后台残留 `snapshot --serve`。日常刷新只写
`--out`。若 Agent Shell 出现 `EAGAIN`，先 `host-pids`，禁止改云端。

Live panel（人工本机终端，单例）：

```bash
python3 spec/meta/tools/ndf_workflow_status.py snapshot --serve --json
```

Open `http://127.0.0.1:8765/`。第二份 `--serve` MUST 被 lock 拒绝。`--topic` is optional. After hops write
`tmp/ndf-canvas-snapshot.json`, the page auto-reloads. Do not curl
`localhost:8081`. htmlpreview is static.

诊断：

```bash
python3 spec/meta/tools/ndf_workflow_status.py host-pids --json
# 显式清理过期 serve：
python3 spec/meta/tools/ndf_workflow_status.py host-pids --kill-stale-serve --json
```

Standalone HTML (Cloud Agent / no local serve):

```bash
python3 spec/meta/tools/ndf_workflow_status.py snapshot \
  --out tmp/ndf-canvas-snapshot.json --json
cd spec/meta/cockpit
npm run build
python3 build_standalone.py
```

Open `docs/ndf-commander.html`. The built page is self-contained and MUST NOT
require GitHub/CDN/network access at runtime. `--topic` selects the unique fat
Topics page. Do not pass `--probe-runtime` on routine refresh; serve Refresh
honors catalog / `--probe-runtime` only and does not force a probe.
Over 120KB compact commander JSON MUST fail and name the overflowing bucket.
Unchanged evidence (Merkle layer hit) MUST reuse persisted spec-health / Replay index
and MUST NOT re-run `ndf_graphcheck`. Commander workbench uses a shallow graph preview or
a cached verified plan; full ACP `create_manifest` stays on pack/repair-pack.
Keep the layout defined in [layout.md](layout.md).
Omit empty sections. Label snapshot time and repository SHA.
After proposal, gate, binder, baseline, or close changes, refresh the snapshot.

Commander actions that may change local evidence MUST use bound action/agent receipts.
The header MUST show payload SHA, absorbed action and latest operation/result/blockers/time.
Only `fresh` permits repair, delegation or close; `refresh_in_progress`,
`stale_after_action` and `unknown` block them. UI-local pending state is keyed by
`absorbedActionId` or `payloadSha`, never `snapshotSha`.

## Three-plane routing

- **Product** is the default whenever a product Charter exists. Show local goals, capability
  portfolio, Golden/SLA, product proposals, roadmap and business POCs. Do not put New Genesis here.
- **NDF Control** is the meta-kernel cockpit. It inspects whether `spec/meta/` can
  still guide Product/Topics. Product contracts and POC binders MUST NOT sink into
  META. Genesis is always first (install, or collapsed 「内核已绑定」). Then kernel
  map (meta seeds only), plane-routed spec-health, process proposals and hygiene.
  With no exploring/blocked POC, binder_health is not_applicable (Trunk); do not
  refresh closed binders.
- **Agents** holds named agent identity cards (OpenClaw / Claude Code / Command Agent /
  context-compiler). Agents MUST NOT navigate into Replay.
- **Replay** is button-action replay only (catalog `action_id` + git baseline A + next SHA B).
  Old canvas-ledger / Episode hops are archived under `.ndf/replay/archive/` and MUST NOT
  appear on this page. Layout: one action picker + left (执行回放 from A) / right (主线对照 at B).
  Page buttons are Composer instructions only — MUST NOT claim 已回放. Mutating skills wrap
  `action-begin → operation → action-commit → action-finish → snapshot`.
- NDF Control/Runtime blockers MAY surface as badges on Product, but never as product KPIs.
- If no Charter exists, default tab is NDF Control → Genesis; follow [genesis.md](genesis.md).

## Topic workbench

Topics selector reads `business.topics[]` directory rows. The seven modules render
**only** `business.focusedTopic`. If Canvas `business-topic` ≠ `focusedTopicId`,
show 「打开工作台」 (`snapshot --update-embedded <canvas> --topic <id>`, no
`--probe-runtime`) — same pattern as Replay 「查这条账」. Missing focused MUST NOT
treat `delegation` / `health.findings` as required objects (no crash).

Read a topic in this order:

```text
TOPIC → DESIGN → PERF_BASELINE → DELTA → INTERFACE → GATES → proposals
```

Lead with business hypothesis, expected impact, current evidence and explore surface. Then render
three independent columns:

- Design: goals, hypothesis, DESIGN/INTERFACE, proposals and gaps.
- Implementation: topic code, isolation, COMMITS and Claude Code run state.
- Test: baseline bind, Numbers, evidence, DELTA Hotspot/Rounds and stale state.

Gate state comes only from valid `GATES.md` receipts. File existence is readiness
evidence, never approval. Historical binders without receipts display `legacy_unknown`.

## Actions

Commander buttons copy a self-contained prompt that starts with a slash
Command, a workflow Skill path, and the unique `spec/meta/tools` CLI.
They never approve a gate or run shell directly. Index:
[actions.md](actions.md). Atoms: `.cursor/commands/ndf-*.md`. Orchestration:
[workflows/](workflows/).

**Control vs Implementation routing:**

- NDF Control (legacy gate audit, GATES, binder, proposals) → OpenClaw via
  `control-pack` + [openclaw-delegate.md](openclaw-delegate.md)
- Implementation (POC code, evidence, DELTA Numbers) → Claude Code via `pack` +
  [acp-delegate.md](acp-delegate.md)

Topic actions follow `inspect → structured finding → bounded repair → recheck → refresh`.
Use `topic-health`, not a hand-built sequence of perf/isolation/pack buttons. A perf
binding header or binder finding routes to OpenClaw; Numbers/evidence and isolation/code
repair route to Claude Code. Human gate phrases remain manual.

NDF Control uses `spec-health` for meta/product graph, index, binder and
proposal-plane conformance. Repair is plane-routed: meta graph / missing seeds →
`ndf_improvement_proposal`; product graph → Product; binder instance → Topics.
工作流演进 also has an always-visible human-intent entry. It invokes the same
project task with `origin=human_intent`, intent SHA and an explicit Episode, and
does not require a health finding. Finding-driven repair uses
`origin=health_finding`; do not merge these two sources in the UI.
After a process proposal exists, 工作流演进 MUST show a focused hop CTA
（推进：已确认 / 推进：已审核）using `ndf_improvement_land`. Intake stays available
but is not the next action. OpenClaw process draft delegation must name
`ndf_improvement_proposal`, stamp `Status: Pending confirmation`, and MUST NOT
copy product clauses or POC binder fields into `spec/meta/`. Landing stable META
happens only after the human phrase 已确认 on the land hop. NDF Control never
delegates product implementation.

Before Claude Code POC delegation:

1. Run `ndf_workflow_status.py pack --topic <topic> --episode <episode-id> --json`.
2. Require a verified META-012 Task Manifest + role plan and `context-verify`.
3. Require both `static_preflight_passed=true` and `runtime_dispatch_ready=true`.
4. Require the full pipeline handshake and lease receipt in [acp-delegate.md](acp-delegate.md).
5. Use one manifest SHA across Canvas/OpenClaw/Claude Code; each role keeps its own plan SHA.

## Episode Replay

Per [[META-013]], recording is explicit (`--episode` or `NDF_REPLAY_EPISODE`) and never
captures unrelated chats.

**Canvas Replay main path** (what the human uses):

- First: hop directory from `.ndf/replay`. Unfocused hops: 「查这条账」 then one focused page. Loaded: 人话 + 规范组装 Prompt + 当时实发 Prompt (Prompt default-collapsed). Missing Plan/request MUST show `whyMissing`; never fake a Prompt from graphNodes
- Guest VM 回放这次 hop — after the ledger. Host runs only `ndf_replay.py guest-run --adapter vm`. Proof is guest-proof JSON (`valid=true`, contract `adapter=vm`). Forbid host-mount of live checkout. Prompt/worktree/bwrap are not completed replay. If `environment_blocked` / missing image, follow [ndf-replay-sandbox](../ndf-replay-sandbox/SKILL.md)
- Guest VM 回放到上一步 — same guest-run; report selected prefix only
- Do **not** put workspace write-back on the Replay tab
- Ordered reads MUST be listable from the Context Plan; never pretend Manifest graphNodes are enough
- Do **not** show R3 / counterfactual fork on the Replay tab
- Do **not** fall back to `isolate` / live `reconstruct` when guest-run is `environment_blocked`
- Do **not** use OpenClaw cube-sandbox skill host-mount of `repo_root` for replay

CLI levels remain defined by META-013 (R0/R1/R2/R3) but are not the Canvas landing vocabulary.

Canvas MUST display coverage gaps, join/semantic gaps, per-branch event-chain integrity,
changed files and gate evidence. It MUST NOT display hidden reasoning. Compaction creates a
checkpoint commit; summary-only state cannot dispatch.

Historical integrity and current restore/dispatch readiness are separate. Repository advance,
gate drift, or worktree cleanup MUST NOT turn a valid historical record into “cannot replay”.
Workspace write-back is CLI-only and is not a Canvas Replay action. Composer buttons open
instructions only, never imply Canvas already executed restore.

## Close hops

There is no Close tab. Close is a Topics prompt sequence after
`selected_decision ∈ {reject, promote, partial}`. Canvas is not a live Agent runtime;
`newComposerChat` has no callback. Use [close-console.md](close-console.md). Completion
comes only from refreshed `control.close` evidence on the Topics decision card.

**生成下一步** records `selected_decision`, then runs the first legal hop in the same
chat. After 已审核, continue the close-apply chain in that chat; do not bounce to
Topics for plan / N/A integrate / graph / finalize. MUST NOT say "open the Close page".

The only legal promote sequence is:

```text
promote proposal confirmed/landed/reviewed
→ close-plan
→ Claude Code integration
→ index/graphcheck
→ build/perf/golden
→ TOPIC/COMMITS/NOTES/archive finalization
```

Show `closing` until every required post-check passes. Partial remains `exploring`.
Reject uses DEC/deprecated/archive and does not enter promote integration.

## Supporting references

- [layout.md](layout.md)
- [genesis.md](genesis.md)
- [actions.md](actions.md) — id → command → skill → tool index
- [workflows/](workflows/) — Skill orchestration modules
- [close-console.md](close-console.md)
- [snapshot-schema.md](snapshot-schema.md)
- [acp-delegate.md](acp-delegate.md)
- [openclaw-delegate.md](openclaw-delegate.md)
- [claude-code-pipeline.md](claude-code-pipeline.md)
- [ndf-replay-sandbox](../ndf-replay-sandbox/SKILL.md) — install local KVM guest for Replay
