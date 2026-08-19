---
name: ndf-workflow-canvas
description: >-
  Projects the local business project into a business-first Cursor Canvas, with
  separate Product, NDF Control, and Claude Code Runtime planes plus
  Design/Implementation/Test topic drill-down and strict close actions. Use when
  the user asks for an NDF workflow canvas, product cockpit, Genesis, POC workbench,
  governance health, agent runtime, sandbox delegation, or close visualization.
disable-model-invocation: true
---

# NDF Workflow Canvas

## Authority

Read in this order:

1. `AGENTS.md`
2. `spec/meta/README.md`
3. `spec/meta/language.md` — [[META-008]]
4. `spec/meta/process.md` — [[META-009]]…[[META-013]], [[BEH-025]]
5. `spec/meta/tools/README.md`

Never use `packages/ndf-harness/` or `.cursor/skills/ndf-harness/` as local
process truth. Business truth comes from `spec/00–50` + Trunk; Meta controls flow.
Canvas is a derived projection, not a product or process SoT.

## Open or refresh

1. Run:

   ```bash
   python3 spec/meta/tools/ndf_workflow_status.py snapshot \
     --update-embedded /absolute/path/to/ndf-workflow.canvas.tsx --json
   ```

2. Require `updated=true`; the command atomically replaces the complete SNAPSHOT, verifies
   payload/source/action bindings, and writes a projection receipt. Do not maintain an ad-hoc
   snake_case/camelCase transform.
3. Keep the layout defined in [layout.md](layout.md).
4. Omit empty sections. Label snapshot time and repository SHA.
5. After proposal, gate, binder, baseline, or close changes, refresh the snapshot.

Canvas actions that may change local evidence MUST use bound action/agent receipts.
The header MUST show payload SHA, absorbed action and latest operation/result/blockers/time.
Only `verified_at_generation` permits repair, delegation or close; `pending_refresh`,
`refresh_in_progress` and `unknown` block them. Canvas-local pending state is keyed by
`absorbedActionId` or `payloadSha`, never `snapshotSha`.

## Three-plane routing

- **Product** is the default whenever a product Charter exists. Show local goals, capability
  portfolio, Golden/SLA, product proposals, roadmap and business POCs.
- **NDF Control** holds Genesis, GATES, process proposals and spec health.
- **Agents** holds Claude Code session/run/worktree/lease and completion state.
- **Replay** holds content-addressed Episode history, coverage, timeline and explicit R0/R1/R2/R3 actions.
- NDF Control/Runtime blockers MAY surface as badges on Product, but never as product KPIs.
- If no Charter exists, route to NDF Control → Genesis; follow [genesis.md](genesis.md).

## Topic workbench

Read a topic in this order:

```text
TOPIC → DESIGN → PERF_BASELINE → DELTA → INTERFACE → GATES → proposals
```

Lead with business hypothesis, expected impact, current evidence and explore surface. Then render
three independent columns:

- Design: goals, hypothesis, DESIGN/INTERFACE, proposals and gaps.
- Implementation: topic code, isolation, COMMITS and Claude Code run state.
  Preparing the baseline workspace (`poc_prepare_baseline`) lives on this card after
  「可以开始实现」; it is not page-bottom 「本轮决策 / 生成下一步」.
- Test: baseline bind, Numbers, evidence, DELTA Hotspot/Rounds and stale state.

Gate state comes only from valid `GATES.md` receipts. File existence is readiness
evidence, never approval. Historical binders without receipts display `legacy_unknown`.

## Actions

Canvas actions open files or start a Composer chat with a self-contained command/prompt.
They never approve a gate or run shell directly. Use [actions.md](actions.md).

**Control vs Implementation routing:**

- NDF Control (legacy gate audit, GATES, binder, proposals) → OpenClaw via
  `control-pack` + [openclaw-delegate.md](openclaw-delegate.md)
- Implementation (POC code, evidence, DELTA Numbers) → Claude Code via `pack` +
  [acp-delegate.md](acp-delegate.md)

Topic actions follow `inspect → structured finding → bounded repair → recheck → refresh`.
Use `topic-health`, not a hand-built sequence of perf/isolation/pack buttons. A perf
binding header or binder finding routes to OpenClaw; Numbers/evidence and isolation/code
repair route to Claude Code. Human gate phrases remain manual.

NDF Control uses `spec-health` for project-level meta/product graph, index, binder and
proposal conformance. OpenClaw project delegation must name `ndf_improvement_proposal`;
NDF Control never delegates product implementation.

Before Claude Code POC delegation:

1. Run `ndf_workflow_status.py pack --topic <topic> --episode <episode-id> --json`.
2. Require a verified META-012 Task Manifest + role plan and `context-verify`.
3. Require both `static_preflight_passed=true` and `runtime_dispatch_ready=true`.
4. Require the full pipeline handshake and lease receipt in [acp-delegate.md](acp-delegate.md).
5. Use one manifest SHA across Canvas/OpenClaw/Claude Code; each role keeps its own plan SHA.

## Episode Replay

Per [[META-013]], recording is explicit (`--episode` or `NDF_REPLAY_EPISODE`) and never
captures unrelated chats. Replay actions are distinct:

- R0 Audit: exact stored-object/event verification, no model/tool execution;
- R1 Observation: recorded responses and tool cassettes, no side effects;
- R2 Sandbox Outcome: one joined run's recorded completion/cassettes/lease, complete recorded
  expectations, managed adapter, network/filesystem/process isolation, Context Plan/lease-bounded
  write roots, and cost/side-effect confirmation;
- R3 Counterfactual Fork: new history; any model re-invocation belongs here.

Canvas MUST display coverage gaps (`completion_only`, `messages_only`, unknown hidden surface),
manifest/plan join gaps and semantic receipt/lease gaps, per-branch event-chain integrity, recorded observation policies,
changed files and gate evidence. It MUST NOT display hidden reasoning. Compaction creates a checkpoint commit; summary-only
state cannot dispatch.

Historical integrity/semantics and current restore/dispatch readiness are separate fields. Repository
advance, gate drift, or worktree cleanup may block current restore but MUST NOT turn a valid historical
R0 red. When Canvas can only open Composer, R0/R1 controls MUST be labelled as opening instructions,
not as completed Replay execution. R2 MUST show the evidence-specific adapter, network mode, command
set and write roots before confirmation. Diff is split into manifest, context, events, observations,
results and verification.

## Close wizard

Canvas is not a live Agent runtime. The interactive Close Console MAY collect input and retain
submission history, but Agent replies remain in Composer and `newComposerChat` has no callback.
Use [close-console.md](close-console.md); completion comes only from refreshed
`control.close` evidence.

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
- [actions.md](actions.md)
- [close-console.md](close-console.md)
- [snapshot-schema.md](snapshot-schema.md)
- [acp-delegate.md](acp-delegate.md)
- [openclaw-delegate.md](openclaw-delegate.md)
- [claude-code-pipeline.md](claude-code-pipeline.md)
