# Canvas / commander layout

Primary surface: `spec/meta/cockpit/` (React+D3). Cursor `.canvas.tsx` is a stub
(header freshness + catalog action Open NDF commander). Layout below still governs
the commander tabs. No control exists unless it is in `action-registry.json`.

## Global header

Always show:

- Product name + Charter one-liner
- Repository SHA and snapshot time (`generated_at`)
- Payload SHA + absorbed action + projection freshness + latest action operation/result/blockers/time
- **Refresh snapshot** button (the only full-projection refresh)
- Product-scoped Now / Next / Blocked

Keep five-tab navigation: Product / Topics / NDF Control / Agents / Replay.
There is no Close tab. Close is a Topics hop sequence.
Only `fresh` can enable ready/repair/delegate/finalize actions.

## Navigation

Use persistent tabs:

1. **Product**
2. **Topics**
3. **NDF Control**
4. **Agents**
5. **Replay**

Product is default whenever a product Charter exists. Without a Charter, open NDF Control first (Genesis 安装轨).

## Product cockpit

Order:

1. Product goal, phase and scale coverage
2. Golden/SLA performance and variance warnings. SHA mismatch is expected when HEAD moved; Open Golden is read-only.
3. Product actions: Open Charter, Open Golden, **Align Golden**, then a human-intent block for New Proposal.
   - Only `fresh` enables Align Golden / New Proposal.
   - New Proposal MUST carry human text in 「描述要探索或变更的产品想法」. Empty text disables the button and MUST NOT dispatch; the Agent MUST NOT invent an idea.
   - New Proposal does **not** require an existing topic. OpenClaw researches locally and on the web, then drafts one `spec/open/` proposal. Create `poc/` only after 已确认.
   - New Proposal stays disabled while Golden is missing, unresolvable, or Trunk `src/` `include/` `tests/` changed since the Golden commit (`head_ahead_of_golden`). Repair is Align Golden (re-run matrix or confirm docs-only exemption).
   - `docs_only_ahead` keeps a warning but allows New Proposal when the intent is non-empty.
4. Capability portfolio mapped to Trunk modules
5. Active business topics (directory rows only; no foundation/delegation):
   `Topic | Hypothesis | Surface | Evidence | Baseline | Control blockers`.
   Product **Product proposals**: Implemented rows that match an active `poc/<topic>` show
   「打开 Topics 工作台」 (`openTopic` + Topics 「打开工作台」 if selector ≠ focused).
6. Product-only proposals and roadmap backlog
7. Business risks

Do not show process proposals, Meta clause counts, or Genesis warnings as product KPIs.

## NDF Control

Meta 元内核驾驶舱。只回答：**流程内核能不能安全地指挥 Product / Topics / Agents**。

**不变量**：元工作流只指导项目和 POC。产品契约（`spec/00–50`、`spec/open/`）和装订器实例（`poc/<topic>/ndf/`）不得下陷进 `spec/meta/`。Control 是检查面，不是把上层文档吸进 META 的容器。

分流：元规则坏了 → process 提案写 `spec/meta/open/`。上层实例不合元规则 → 去 Product / Topics 修实例。禁止为了让检查变绿把产品/POC 文档逻辑搬进 META。

Genesis 永远第一；状态只改展开程度。五块按因果链：Genesis → 内核地图 → 自洽性 → Advisor → 工作流演进。

1. **Genesis（永远第一）**
   - 未安装 / greenfield / adopt：展开 G0→G3 门禁。文案是「把流程内核装进本仓」。**New Genesis 只在本页**。
   - `operational` + accepted，以及 `operational_legacy`：默认折叠。摘要一行「内核已绑定 · 日常指挥走 Product / Topics，不必重跑 Genesis」。展开 = 内核能力图例（G0 契约来源 / G1 双轨边界 / G2 写入边界 / G3 验收口径），不是四张 Open 文件卡，不展示产品功能名、SLA 或 TOPIC 字段。绑定 SHA 放进更里层「绑定档案」。accepted 时 New Genesis disabled「不得重跑」。
   - `operational_legacy` 仍可可选 adopt，不阻断 Product/Topics。
2. **NDF 内核地图**（未安装时标题为「将装什么」）— 模块默认折叠；折叠头显示「种子 a/b · 缺 k」。展开后只展示 `spec/meta/graph.json` process profile IR，禁止并入产品 `spec/graph.json`。种子 = META-001…005 / 008…015、CHR-008、BEH-018…020、BEH-025、CON-POC-001。SNAPSHOT `kernelMap.nodes` 省略；表用 `seeds`。缺失 = 指挥层可能漏读双轨/装订/晋升规则；补齐走 OpenClaw process 提案，禁止用产品提案或改 TOPIC。标明 scope=ndf-process。Open `language.md` / `process.md` / meta README。
3. **内核自洽性** — 折叠头：`内核自洽 · 阻断 n · 告警 m · 通过 k` + 失败检查胶囊。展开四列：检查 / 原因 / 阻断了哪层指挥 / 修哪一平面。禁止大段 evidence、TOPIC YAML、产品条款正文。CTA 按平面：`meta_graph` → `OpenClaw: 修内核（process 提案）`；缺种子 CTA 在内核地图；`product_graph` → 去 Product；`binder_health` → 去 Topics（仅当 Topics 仍有 exploring/blocked POC）。**无活跃 POC 时** `binder_health` 为 `not_applicable`（回退 Trunk）：不跑 `--all-topics`，不算失败，不渲染「去 Topics」，不必为关闭装订器刷新。适用检查全过即可（Trunk 时 3 检：meta / product / index）。`index_consistency` 按失败 ID 分流，禁止一键写 meta。`proposal_plane` 用一句话说清：process 必须在 `spec/meta/open/`，产品必须在 `spec/open/`。Advisor 只读，不能补种子/改 binder/关告警，也不能建议把产品/POC 写入 meta。
4. **工作流演进** — 只演进 `spec/meta/`。**下一步**是流程内核的单一演进建议（补种子 / 修元图 / 推进已有 process 提案 / 无强制演进），不是自洽性 finding 的复述，也不是产品/POC 修复清单。其下 MUST 始终显示 human-intent 输入框「描述要改进的 META 工作流」与「提交流程改进」；不得因已有 proposal、缺种子或 health finding 隐藏。空输入不派发，且不得粘贴产品条款、POC 实例字段或 SLA 数字。该入口走 `project-control-pack --origin human_intent` + Episode + OpenClaw request/response，只起草 `spec/meta/open/` 提案并写 `Status: Pending confirmation`，然后刷新。有聚焦 process hop 时，演进区的**主 CTA 是「推进：已确认」或「推进：已审核」**（`ndf_improvement_land`）；提交流程改进退为次按钮，仍可开新提案。推进按钮打开审阅聊天，**不得**把点击当成批准；人发出精确口令后 OpenClaw 才落地或标 reviewed。禁止静默改 stable meta；落地只发生在推进 hop 且人已发「已确认」之后，由 OpenClaw 执行。禁止改 `.openclaw/state.json`。Process 提案目录可折叠，只列待审元组 `[title, hop|status, path]`（waiting hops + managed Implemented-未审核）；历史 Implemented 无绑定回执的计入 `archivedCount`。**不要**为打开 md 做一排按钮，路径仅作定位。Implemented 但未审核的 **managed** 提案仍留在目录，直到「已审核」。
5. **执行面卫生** — `legacyUnknownTopics` / `invalidatedReceipts` 计数。细节去 Topics。

未安装时 3–5 默认收成占位，避免空表喧宾夺主。产品实现按钮永不出现。
New Genesis 不在 Product。无 Charter 时默认 tab = NDF Control。

## Topics

Selector reads `business.topics[]` directory rows. Seven modules render **only**
`business.focusedTopic`. If `selected !== focusedTopicId`, the workbench area
shows 「打开工作台」 (`snapshot --out … --topic <id>`, no
`--probe-runtime`) instead of empty `delegation` / `health.findings`. Missing
focused MUST NOT crash.

Seven modules, top to bottom. Do not restore the old 18-block dump.

1. **TOPIC 总览（只读）** — `TOPIC.md` 的 `概述` / `Summary` 简短总结 + lifecycle + Open TOPIC.md。不得堆 explore surface、proposal path、evidence、blocker 或 decision 元数据。
2. **三空间可靠性** — Design / Implementation / Test. Each card: ready pill, one-line purpose, gaps with **why blocked + how to fill** (not gap-id only), 1–3 NDF clause refs and blocker count. **Decision fields for the page read `business.focusedTopic` workbench**, never the directory row. **Design** is status-only; gate/binder dispatch lives in module 7. **Implementation**: code gap summary + always-visible `poc_prepare_baseline` when gap `missing_baseline_workspace` exists; `poc_isolation_repair` when a matching finding exists; pointer only（「本轮决策在页底」）— **no** decision composer here. **Test**: Open DELTA.md; **补测 / 写 DELTA** always visible when gap `numbers_pending` exists **or** a measurement-owned finding is present (e.g. `vs_unmentioned`, `empty_numbers`, `unverified_measurement_claim`) via `gapMeasurementWork` (independent of `selected_decision`). Repair composer buttons MUST remain visible when the matching gap exists; they copy a Prompt and MUST NOT be hidden solely because projection freshness is stale. No **命令入口** Callout above the grid — that lives on module 7. **Delegate POC / Prepare ACP lease MUST NOT appear on any space card**.
3. **阻塞与修复** — Refresh topic / Diagnose topic + meta/product graphcheck pills. One table of **NDF 依据** only (Clause ID, title, space, kind). Do not repeat three-space blocker prose, evidence walls, or repair buttons (those live on the space cards). Diagnose hop next step routes to the matching **space card** or page-bottom **本轮决策与实现委派**, not back to this table for repair buttons.
4. **NDF 基础追溯** — collapsed by default. Product graph nodes (`scope != ndf-process`), stable/draft counts, depends-on edges, simplified surface → design → code → verification table. Expand to see tables.
5. **NDF 工作流 / Meta** — collapsed by default. Process/meta nodes and spec-health state. Label: 流程约束，非产品功能契约.
6. **机械上下文** — collapsed by default. One-line summary: role, plan SHA, read count, graph nodes/depth. Order is META-012 binder read order, not file-creation order. Expanded: first 5 ordered reads, clause seeds, delegation write/forbid roots. No duplicate baseline numbers.
7. **本轮决策与实现委派** — last Card is the **only** full-topic command surface: top **命令入口** Callout (`nextStepLine`); then separate **OpenClaw Control pipelines** cards（人工门禁 3 闸 / 装订器 6 面 / 同假设修订，带 checklist、dispatch 状态与 handoff）；then **本轮决策** (offered prefill chips + TextArea + **生成下一步**); finally **Claude Code 实现委派** (Delegate POC + Prepare ACP lease) and close-hop recovery. Decision composer and Control pipeline buttons MUST NOT live on a space card. Gate/binder pipeline buttons MUST stay clickable to copy a Prompt even when the current projection is stale or the pipeline currently has no missing facet; `needed=false` means “可复检”，not “隐藏按钮”. Delegate POC stays **visible and disabled** until `selected_decision` is implement or continue_exploring **and** static/runtime preflight (including graphcheck) is ready.

Control repairs MUST route through two pipelines: **人工门禁（3 闸）** via
`gate_pipeline` / gate step tasks, and **装订器修订（6 面）** via `binder_pipeline` /
`binder_amend`. Prefer one Cursor dispatch per pipeline with Episode resume; do not
flatten both into identical unlabeled buttons or call binder facets 闸.
Gate owns only `GATES.md`; if a bundle facet is missing, show
`blocked_by_binder → next_binder_facet` and route to the page-bottom binder pipeline card. Binder owns only
the focused facet and may no-op recheck complete files. It never approves gates.
If projection sets `force_new_episode`, start a **new** Episode (no `--resume`, new
`request_id`) — stale Episode cannot rebind after manifest/context drift. Gate SHA
mismatch on audit/pipeline tasks is work to do, not a reason to skip OpenClaw.
Gate/binder Control packs go through `control-pack` + OpenClaw. Isolation/code/Numbers
repairs route through Claude Code `repair-pack`. `unverified_measurement_claim` and
`numbers_pending` MUST be Claude Code Run measurement, never binder_amend. Binder only
repairs bind-skeleton kinds (`missing_vs`, `missing_config*`, `unknown_vs`). Generic
“Delegate to OpenClaw”, standalone perf/isolation buttons, and user-facing prepare-pack
buttons are not shown.
Each pipeline card MUST show `尚未派发 / 正在准备 / 已发送 / OpenClaw 已接收 /
等待人口令 / 执行中 / 阻塞`; only a recorded OpenClaw response may show “已接收”.
Blocked cards expose retry using the same request identity.
After all three gates are valid, show `decision_required` on the **page-bottom 本轮决策与实现委派** card (offered prefill chips + TextArea + 生成下一步), not on the Implementation space card and not six work-mode buttons buried elsewhere. The third gate phrase `可以开始实现` is only permission to
write `poc/` code. Prefill chips use snapshot `decision.offered` (do not hardcode implement).
The human writes the next decision in that TextArea; chips only prefill. One **生成下一步** action maps
the text to a real NDF hop. Close modes record `selected_decision` then execute the
first legal close hop in the same chat (`control_proposal` if unreviewed, otherwise
the close-apply chain). After 已审核, continue plan → skip N/A integrate →
graphcheck → finalize in that chat. Topics “继续关闭收口” is recovery only.
There is no Close tab.
Hypothesis fork is `new_poc` (product proposal + sibling topic), never in-topic
`amend`; `amend` is same-hypothesis binder tweak only.
Empty text MUST NOT dispatch and MUST NOT default to `continue_exploring`. NDF
modes remain the assembled `selected_decision`, not the first UI. Do not infer
Close from negative-result prose. `new_poc` MUST NOT write `selected_decision`
on the current topic.
Until `TOPIC.md` has `selected_decision` of implement or continue_exploring, Delegate POC stays **visible and disabled**. Claude Code markdown
reports are never the next command surface.

Never use a green ready state when Numbers are pending, baseline is stale, or a gate is
`legacy_unknown|invalidated`.
Gate SHA details stay on the Design space card; review-slice mode hashes contract
slices only; mutable PERF Numbers, DELTA Rounds, evidence, COMMITS and GATES
must not cause gate drift. Missing/invalid slices and legacy→slice mode mismatch are blockers.

## Agents

Show named identity cards (Command Agent / OpenClaw / Claude Code / context-compiler):

- one-line role, provider/session, write roots, tools/lease, reachability and current blockers
- Command Agent is the human-facing Commander/Composer role; its state comes from
  projection freshness + latest action and it MUST NOT be labeled Canvas
- each card has 「用该身份查看 Replay」 → set `replay-agent-filter-v1` then switch
  to Replay. Keep the current hop if it still matches the lens; otherwise the first
  listed hop. Do not clear hop selection. This is an **identity lens**, not a shared dump.

Do not put a second timeline on Agents. Runtime probe notes come from header
**Refresh snapshot** (`--probe-runtime`); do not add duplicate Inspect buttons.

## Replay

Replay answers: **did this Commander button action reproduce from git baseline A?**

Main path (no plane/agent filters, no 人话/规范/实发 Prompt, no 查这条账):

```text
1. Pick one button action (requires baselineSha A + resultSha B from action-commit)
2. Left: 「执行回放」 → Composer Prompt opens worktree at A and re-runs the recorded button Prompt
3. Left lower: replay git status (pending until human runs the Prompt)
4. Right: 「打开主线对照」 → detach/show at B; git show / git diff A B
5. Empty directory: 「尚无带 git A/B 的按钮动作」; legacy ledger is archived
```

| Action | Meaning |
| :--- | :--- |
| 执行回放 | Instructions: `command-replay --button-action` at A; MUST NOT claim 已回放 |
| 打开主线对照 | Instructions: compare-only at B; MUST NOT claim 已回放 |

Legacy canvas-ledger / Episode hops live under `.ndf/replay/archive/` (CLI archaeology only).
Guest VM / R0–R3 remain CLI optional ([[META-015]] / [[META-013]]), not Commander main path.
Agents MUST NOT jump to Replay.

Projection fields: `actionId`, `baselineSha`, `resultSha`, `prompt`, `left`, `right`,
`originalDiffStat`, `archivedNote`.

## Close hops (on Topics)

Close is not a sixth tab. Snapshot `control.close` is a read-only progress table on the
Topics decision card after `selected_decision` is `reject|promote|partial`.

After 已审核, Composer runs the close-apply chain in the same chat via
[close-console.md](close-console.md). The Topics button is recovery when the human
left the chat or the chain stopped on ACP / a blocker. Label reject N/A
「继续关闭收口」, not 「委派合入 / 处置代码」.
Promote / partial / reject remain separate branches. Prefix steps with plane:

1. Business: evidence ready
2. Control: proposal reviewed
3. Control: read-only close plan
4. Runtime: Claude Code integration (N/A when `trunk_src_writes=none`)
5. Control: index/graphcheck
6. Business: build/performance/golden
7. Control: final binder close

Every close prompt MUST name the tool, human gate (if any), POST_ACTION_SYNC, and
that remaining mechanical steps stay in this chat. MUST NOT say "open the Close page".
