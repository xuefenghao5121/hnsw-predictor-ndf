# Canvas layout

## Global header

Always show:

- Product name + Charter one-liner
- Repository SHA and snapshot time (`generated_at`)
- Payload SHA + absorbed action + projection freshness + latest action operation/result/blockers/time
- **Refresh snapshot** button (same as Product tab full refresh)
- Product-scoped Now / Next / Blocked

Keep one six-tab navigation: Product / Topics / NDF Control / Agents / Replay / Close.
Only `verified_at_generation` can enable ready/repair/delegate/finalize actions.

## Navigation

Use persistent tabs:

1. **Product**
2. **Topics**
3. **NDF Control**
4. **Agents**
5. **Replay**
6. **Close**

Product is default whenever a product Charter exists. Without a Charter, open NDF Control/Genesis.

## Product cockpit

Order:

1. Product goal, phase and scale coverage
2. Golden/SLA performance and variance warnings
3. Capability portfolio mapped to Trunk modules
4. Active business topics:
   `Topic | Hypothesis | Surface | Evidence | Baseline | Control blockers`
5. Product-only proposals and roadmap backlog
6. Business risks

Do not show process proposals, Meta clause counts, or Genesis warnings as product KPIs.

## NDF Control

Contains Genesis, GATES, process proposals and project-level NDF conformance:
meta/product graph, index consistency, all-topic binder health, gate summary and proposal hygiene.
It provides one NDF Control check, read-only Advisor diagnosis, and a specifically named
OpenClaw NDF improvement proposal action. Product implementation is never delegated here.

Genesis rail:

Four-step rail:

```text
G0 IDEA → G1 Foundation → G2 Trunk Candidate → G3 Freeze
```

Each step shows gate state, bound content SHA, gaps, and the exact next phrase/file.
Keep project goal golden separate from performance Golden Baseline.

## Topics

Top: business hypothesis, expected impact, current evidence and explore surface.

Middle: Design / Implementation / Test columns, then explicit gate/control blockers.

- Design
- Implementation
- Test

Implementation 准备基线工作区（第三闸已过、拷对照代码进 `poc/<topic>/`）是 Implementation 卡 hop，
不是页底「本轮决策 / 生成下一步」。生成下一步只记录 `selected_decision`（实现 / 继续探索 / 早关）；
空文本与未核验投影不得派发。基线缺口时禁用生成下一步，并说明先在 Implementation 准备。
第三闸未过时 Implementation 文案指向 Design 门禁，禁止拷代码。

Bottom:

- Gate status table: `topic_review / design_review / implementation_approval` + SHA state
- Gate columns: expected SHA / approved SHA / match; preserve human sequence
- Topic check state / exit / summary, diagnosis freshness/time, and Resolved/Remaining/New diff
- Context Preview: plan SHA, explicit role/task/track, ordered reads, seeds, graph hops and
  truncation, implementation surface, baseline and privileges
- `next_human_phrase` callout when pending
- DELTA bridge: Feature → Hotspot → latest Round
- traceability table: clause/goal → design → code/commit → verification
- structured findings table:
  `Space | Severity | Finding | Evidence | Repair owner/task | Allowed root | Human gate | Plan SHA`
- contextual actions split into:
  - **Inspect**: Refresh topic | Diagnose topic | Open business topic
  - **Repair**: only deduplicated actions from `health.next_actions`
  - **Delegate**: POC only when gate + full perf bind + isolation preflight are green

Control repairs (`legacy_gate_audit`, gate SHA, gate draft, binder amend) MUST route
through `control-pack` + OpenClaw. Isolation/code/Numbers/baseline-workspace repairs route through
Claude Code `repair-pack`. Generic “Delegate to OpenClaw”, standalone perf/isolation
buttons, and user-facing prepare-pack buttons are not shown.

Never use a green ready state when Numbers are pending, baseline is stale, or a gate is
`legacy_unknown|invalidated`.

## Agents

Display `pipelineReachable`, `activeRuns`, `cliAvailable`, `probeNote`, session/run IDs,
worktree, allowed root, lease and completion receipt. Show `stateExists` separately from
workspace `state` / `match`; a state file alone is never “bound”. Surface OpenClaw degraded.

## Replay

Display local Replay `fsck`, Episode list, selected manifest/role plan, coverage and join gaps,
per-branch event-chain integrity, tool/model observation policy, gate evidence, changed files,
event timeline, branch/head and comparison target. Present R0 Audit, R1 Observation,
R2 Sandbox Outcome and R3 Counterfactual Fork as separate actions.

R0/R1 MUST NOT call a model or live tool. R2 requires one joined run's recorded completion,
sandbox cassettes and lease; expectations MUST be recorded and cover every output, while write
roots remain within both Context Plan and lease. It also requires explicit
sandbox/network/filesystem/process/write-root/cost/side-effect acknowledgement. R3 always
creates new history. Show checkpoint as an append-only commit after context/gate/repo reverify;
summary-only state is navigation and cannot dispatch.

Show `historicalIntegrity`, `historicalSemantics`, `currentRestoreReady` and
`currentDispatchReady` independently. The selected Episode also shows the actual Manifest intent,
seeds and gate/baseline summary plus ordered role-context reads and write roots. Composer-routed
R0/R1 buttons say “open instructions”; they never imply execution. R2 confirmation is tied to the
selected Episode's concrete adapter/network/commands/write roots. Diff has six sections:
manifest/context/events/observations/results/verification.

## Close wizard

Show an **Open Close Console** action plus an evidence-backed step list. The Console is a
custom Canvas dialog (topic / mode / step / instruction), not embedded live chat.

Show promote and reject as separate branches. Prefix each step with its plane:

1. Business: evidence ready
2. Control: proposal reviewed
3. Control: read-only close plan
4. Runtime: Claude Code integration
5. Control: index/graphcheck
6. Business: build/performance/golden
7. Control: final binder close

Final close action remains disabled until every required item is green.
Partial is a third explicit branch; it keeps the topic `exploring`.

The step list MUST come from snapshot `control.close`, including receipt state and source path.
Render `legacy_unbound` / `missing` as blockers.
Unknown tool/evidence state remains pending. Clicking a step MAY open the Console at that step.

Console controls:

- Send operation (disabled when proposal/plan prerequisites are absent)
- Refresh dashboard
- Close
- local submission history labelled `dispatched`, never `completed`

Every operation MUST follow [close-console.md](close-console.md) `POST_ACTION_SYNC`.
