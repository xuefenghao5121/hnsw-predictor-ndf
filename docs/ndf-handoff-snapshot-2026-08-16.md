# NDF 工作交接（刷新至 2026-08-18）

> **文档性质：历史交接快照，非 NDF SoT。** 指挥以 [`docs/ndf-workflow-handoff.md`](ndf-workflow-handoff.md) 为准。
> 本文件来自 `cursor/cloud-agent-1787136015374-pev95` 合入时的战场记录，保留供审计。
>
> 冲突一律以 [`spec/`](spec/)、[`spec/meta/`](spec/meta/) 和各 topic 的
> `poc/<topic>/ndf/TOPIC.md` 为准。
>
> 初始审计：2026-08-16  
> 本次刷新：2026-08-18（page-packer reject 收口；Canvas 磁盘查账；Replay 必选 hop；
> Control 无活跃 POC 时装订器检查回退 Trunk）  
> 仓库：`/home/huawei/hnsw-predictor-ndf`  
> 分支：`cursor/ndf-context-compiler-c8d2`（领先 origin 2 commit）  
> HEAD：`a14339234133cc6c5a2348464954f744c6465efb`

## 1. 一页摘要

NDF 已从「规范文件 + POC 目录」变成可机械验证的本地工作流。产品 SoT 与 META
process SoT 分层；POC/Trunk 双轨、装订器、promote/reject、Context Compiler、
Episode Replay、五 Tab Canvas 都已在用。

**当前战场状态（2026-08-18）：**

| 面 | 状态 |
|---|---|
| 产品 / Trunk | operational；Golden 仍锚在 `7ee4ee2`，HEAD `a143392` **ahead** |
| 活跃 POC | **0**。page-packer 已 reject（DEC-100），Topics 空，`now=DiskHNSW Trunk` |
| 指挥 state | `.openclaw/state.json` 仍写 `active_topic=page-packer`（残留，非 SoT） |
| Canvas 投影 | embedded `projectionFreshness.state=stale_after_action`（close-reject-apply 之后未再官方 Refresh） |
| New Proposal | Product 上 **disabled**：只认 `fresh`，当前不是 |
| 内核自洽 | 代码已：无活跃 topic 时 `binder_health=not_applicable`（Trunk 三检）。嵌入快照仍是旧的 `--all-topics` failed，需 Refresh 才落盘 |

**接手者立刻要做的一件事：** 页头 **Refresh snapshot**（`--update-embedded` + 验证 receipt）。
在 `fresh` 之前，Product 的 New Proposal、Topics 委派、Control 写动作都不应派发。

## 2. 权威边界与读序

| 优先级 | 来源 | 用途 |
|---:|---|---|
| 1 | [`spec/`](spec/) | 产品 NDF SoT |
| 1 | [`spec/meta/`](spec/meta/) | process profile SoT |
| 2 | [`AGENTS.md`](AGENTS.md) | 指挥工作流与写入边界 |
| 3 | [`spec/meta/tools/`](spec/meta/tools/) | 治理 / 上下文 / 回放 / Canvas 投影 |
| 4 | topic binder | POC 当前状态（非 Trunk SoT） |
| 非 SoT | 本文、`MEMORY.md`、Canvas snapshot、`.openclaw/state.json` | 导航或本地运行态 |

禁止用 `packages/ndf-harness/` 反推本地 `spec/meta/`。

接手读序：`AGENTS.md` → `spec/meta/README.md` → `language.md` → `process.md` →
`tools/README.md` → `.cursor/skills/ndf-workflow-canvas/SKILL.md`。

## 3. Git 与工作区

已提交锚点仍是 `a143392`（process: close replay audit gaps）。产品/POC 相关：

| SHA | 内容 |
|---|---|
| `7ee4ee2` | Promote cluster reorder（BEH-037） |
| `4a70704` | Golden `bl-trunk-golden-7ee4ee2` |
| `9df8b74` | bfs-cluster R0 负结果 |
| `616bfef` | page-packer R0 边际 +1.4% |
| `a9c76de` | cluster-gbdt R0 无显著收益 |

未提交 WIP 仍是主风险（skill / tools / AGENTS / INDEX / 关闭文档 / Canvas 逻辑）。
未跟踪：`.worktrees/`、本文件、`skills-lock.json`。不要 `git add .`。

`.openclaw/state.json` 不是 SoT。Canvas MUST NOT 改它（[[META-011]]）。
当前残留：`active_topic=page-packer`、`control=close_reject_finalize`、
`current_proposal=spec/archive/2026-08/proposal-reject-page-packer.md`。
**不得**把这个残留当成还要刷新 binder_health 的理由。

## 4. 2026-08-17 → 08-18 实际进展

### 4.1 Draft Mapping（已收口，不再卡住）

[`spec/meta/open/proposal-meta-draft-mapping.md`](spec/meta/open/proposal-meta-draft-mapping.md)：

- `Status: Implemented on 2026-08-17`
- `reviewed: 已审核`

旧交接里「已确认但未落地」已过时。

### 4.2 page-packer 负结果关闭（DEC-100）

Human：本方向已无继续价值，reject，不改 Trunk `src/`。

| 产物 | 路径 |
|---|---|
| DEC | [`spec/decisions/32-page-packer-reject.md`](spec/decisions/32-page-packer-reject.md) `{#DEC-100}` |
| 提案归档 | [`spec/archive/2026-08/proposal-reject-page-packer.md`](spec/archive/2026-08/proposal-reject-page-packer.md) |
| Binder 归档 | [`spec/archive/2026-08/poc-page-packer/`](spec/archive/2026-08/poc-page-packer/) |
| live TOPIC | `status: rejected`，`rejects_dec: DEC-100` |
| Integrate | N/A（`trunk_src_writes=none`） |
| graphcheck | meta `hard_errors=0` |

同批已关闭：`bfs-cluster`（DEC-098）、`cluster-gbdt`（DEC-099）。
已晋升：`vecblock-cluster-reorder`（BEH-037 / DEC-096）。

**没有 exploring/blocked POC。** 下一产品动作是开新 topic（Product New Proposal /
roadmap），不是继续 page-packer。

### 4.3 Canvas：磁盘查账（Replay 不再内嵌整本）

真值仍是 `.ndf/replay`。嵌入快照只带：

- slim `episodes[]` 目录（无 Prompt 正文）
- 一个 `replay.focused` 账本页（`--replay-episode`）
- compact JSON；超 120KB 失败

未 focused 的 hop 显示「查这条账」。例行 snapshot **去掉** `--probe-runtime`，
只留页头 Refresh。

### 4.4 Replay 必选 hop

[`ndf-workflow.canvas.tsx`](/home/huawei/.cursor/projects/home-huawei-hnsw-predictor-ndf/canvases/ndf-workflow.canvas.tsx)：

- 列表非空必须保持一个 hop；忽略空值/取消选定
- 筛选后仍在列表则保留，否则落到第一项
- Agents「用该身份查看 Replay」只切 lens，不清 hop
- 时间线步骤仍可清空

### 4.5 Control：无 TOPIC 时装订器检查回退 Trunk

Topics 只投影 `exploring|blocked`。`spec_health()` 已对齐：

- 零活跃 topic：`binder_health = skipped_check(...)`，`not_applicable`，**不跑**
  `ndf_bindcheck.py --all-topics`
- 不产生 `binder_health_failed`
- Trunk 三检照旧：`meta_graph` / `product_graph` / `index_consistency`
- UI：n/a 不算失败；不渲染「去 Topics」；Advisor 不得把关闭装订器当 process 提案

`ndf_bindcheck.py --all-topics` 的 CLI 语义未改。单测已覆盖空 topic / 有活跃 topic。

嵌入 SNAPSHOT 仍是 2026-08-18T09:01 的旧投影（`binder_health=failed` 扫 28 个关闭目录）。
**Refresh 之后**才会变成 `not_applicable`。UI 在 Topics 为空时已按 Trunk 展示，
即使旧 snapshot 仍写 failed。

## 5. Product 页：为什么不能 New Proposal，为什么只有打开文档

这是设计 + 当前闸门，不是按钮坏了。

### 5.1 New Proposal 被禁用的直接原因

Product 上：

```ts
disabled={!projectionVerified}
```

`projectionIsVerified` **只**在 `projectionFreshness.state === "fresh"` 时为真。

当前嵌入快照：

| 字段 | 值 |
|---|---|
| `projectionFreshness.state` | `stale_after_action` |
| 最近动作 | `close-reject-apply`（page-packer，success，08:04Z） |
| `embeddedProjection.status` | `unknown` |

[[META-011]] / Canvas skill：任何可能改证据的动作之后必须
`action-finish → snapshot --update-embedded → verify receipt`。
收口成功后投影变 stale，**在官方 Refresh 验过之前不得再派写动作**。

`Open product Charter` / `Open Golden` 是 `openFile`，只读，不受该闸。

解法：页头 **Refresh snapshot**，等到 header 显示 `fresh`，New Proposal 才会亮。

### 5.2 为什么 Product 只有打开文档、没有修复指导

Product 是**业务驾驶舱**，不是修复工作台：

| 页 | 回答的问题 | 写动作 |
|---|---|---|
| Product | 产品目标 / Golden / 能力 / 路线图 / 风险 | 仅 New Proposal（需 fresh） |
| Topics | 这个 POC 三空间是否完备、闸/装订怎么修 | Diagnose / Repair / 决策 / Delegate |
| NDF Control | META 内核能不能指挥上层 | spec-health / Advisor / process 提案 |

因此 Product **故意**不放「修 index」「改 charter draft」「重跑 Golden」按钮：

- `index_consistency` 悬空引用 → Control / index 平面分流，不是产品 KPI
- `proposal_plane_misfile`（`spec/open/proposal-golden-baseline-rerun-7ee4ee2.md` 标了 `track=process`）→ Control
- `missing_draft_map_entry`（CHR-004 / ARCH-006 / VER-031）→ Control process
- Golden `head_ahead_of_golden`、512MB 16T CV=6.0% → 风险表 + Open Golden，重跑走提案
- 无活跃 POC → 「没有进行中的业务 POC」，修复行不会出现（那些行在 Topics）

风险表（stale_baselines / golden_variance / architecture_debt）是只读告警，
证据列指向文档或关闭 topic 名，**没有 CTA**。要修：Refresh → New Proposal
（新产品/POC）或去 Control（卫生），不要在 Product 上发明一键修。

New Proposal 亮起后的约定（[`actions.md`](.cursor/skills/ndf-workflow-canvas/actions.md)）：

- 先按 `AGENTS.md` 判定 **一个** track
- 产品 → `spec/open/proposal-*.md` + `control-pack --task control_proposal`
- 流程 → `spec/meta/open/proposal-meta-*.md` + `project-control-pack`
- 停在「已确认」；无活跃 topic 时不要再 `--topic page-packer`

## 6. Canvas 五 Tab（现行）

| Tab | 职责 |
|---|---|
| Product | Charter、Golden/SLA、能力、产品提案、风险；无活跃 POC 时显示 Trunk |
| Topics | 空：无 exploring/blocked。Close 不是独立 Tab |
| NDF Control | Genesis 已绑定；自洽性按平面分流；无 topic 时 binder 回退 Trunk |
| Agents | 身份卡；跳 Replay 只切 lens |
| Replay | 磁盘目录 + 一个 focused 账本；必选 hop；查这条账按需加载 |

Close 仍是 Topics hop。现在 Topics 空，关闭链已结束。

## 7. META 能力（仍有效，不重复展开）

语言 / 双轨 / 装订 / Genesis / 门禁切片 / 双流水线 / Context Compiler /
Episode Replay（R0–R3）见 08-16 审计结论，条款未改：

- META-001…015、CHR-008、BEH-018…020、BEH-025、CON-POC-001、ARCH-008
- ADR-META-001 / 002、ADR-TOPIC-BINDER-001、DEC-HYGIENE-001

内核种子地图当前齐全（`missing_seeds=[]`）。Genesis accepted，日常不必重跑。

## 8. 产品与关闭账本

现行 Golden：`bl-trunk-golden-7ee4ee2`（HEAD 超前，未按 META-006 重跑 12 点）。

| ID | 路径 | 作用 |
|---|---|---|
| DEC-084 | `spec/decisions/20-sustained-benchmark-methodology.md` | sustained 方法 |
| DEC-095 | `spec/decisions/095-promote-cqe-peeking.md` | CQE peeking 晋升 |
| DEC-096 | `spec/decisions/096-promote-cluster-reorder.md` | cluster reorder 晋升 |
| DEC-098 | `spec/decisions/30-bfs-cluster-reject.md` | BFS cluster 负结果 |
| DEC-099 | `spec/decisions/31-cluster-gbdt-reject.md` | cluster GBDT 负结果 |
| DEC-100 | `spec/decisions/32-page-packer-reject.md` | page-packer 负结果 |

P3 roadmap 仍在 Product：CSR 上盘、1-hop 预取、PQ mmap 等。下一探索应从这里
（或产品提案）开**平级新 topic**，`depends_on_topics` 写清旧题；禁止把
rejected 的 page-packer 改回 exploring。

## 9. 卫生欠账（Refresh 之后仍在）

这些不是「没有修复按钮」造成的，而是尚未开提案：

1. `index_consistency`：约 8 个 dangling_refs（含 DEC-099/100 → BEH-037 等）。按失败 ID 平面修，禁止一键写 meta。
2. `proposal_plane_misfile`：`spec/open/proposal-golden-baseline-rerun-7ee4ee2.md` 目录是产品、track 写了 process。
3. draft-map：CHR-004 / ARCH-006 / VER-031 为 draft 但无 `spec/meta/open/draft-map/` 行。
4. `poc/` 大量已关闭 TOPIC.md 仍在；`--all-topics` 会扫到它们，**Control 在 Topics 为空时已跳过**。
5. `spec/meta/open/` 大量 Implemented process 提案未归档。
6. Golden 与 HEAD 不对齐；512MB 16T CV 超标（观测，不是立刻改 SLA）。
7. 大段未提交 WIP。

## 10. 推荐接手顺序

1. **Refresh snapshot**（managed Canvas 绝对路径 + `--update-embedded`；页头可带 `--probe-runtime`）。要求 `updated=true` 且投影 `fresh`。
2. 确认 Product：New Proposal 可点；Control：`binder_health=not_applicable`；Topics 仍空。
3. 决定下一跳（只选一条，先提案）：
   - 新产品/POC → Product New Proposal，`track=poc`，平级 topic；
   - 卫生 → Control「提交流程改进」或按平面拆 index / proposal_plane / draft-map；
   - 金标 → 另开产品/verification 提案，不要在 Product 上假装已对齐。
4. 拆分审查未提交 WIP，再考虑提交。不要混入 `.worktrees/` / `tmp/`。

回归（工具层，不替代 Canvas fresh）：

```bash
python3 spec/meta/tools/test_ndf_workflow_status.py \
  WorkflowHealthTest.test_spec_health_skips_binder_when_no_active_topics \
  WorkflowHealthTest.test_spec_health_runs_bindcheck_when_active_topics_exist \
  WorkflowHealthTest.test_active_poc_topic_ids_skips_closed_binders -q
python3 spec/meta/tools/ndf_graphcheck.py --meta --format text --report -
```

## 11. 路径速查

| 目的 | 路径 |
|---|---|
| 指挥 | [`AGENTS.md`](AGENTS.md) |
| META | [`spec/meta/README.md`](spec/meta/README.md) |
| Workflow 工具 | [`spec/meta/tools/ndf_workflow_status.py`](spec/meta/tools/ndf_workflow_status.py) |
| Replay | [`spec/meta/tools/ndf_replay.py`](spec/meta/tools/ndf_replay.py) |
| Canvas skill | [`.cursor/skills/ndf-workflow-canvas/`](.cursor/skills/ndf-workflow-canvas/) |
| Managed Canvas | `/home/huawei/.cursor/projects/home-huawei-hnsw-predictor-ndf/canvases/ndf-workflow.canvas.tsx` |
| Golden | [`spec/50-verification/golden-baseline.md`](spec/50-verification/golden-baseline.md) |
| page-packer 归档 | [`spec/archive/2026-08/poc-page-packer/`](spec/archive/2026-08/poc-page-packer/) |
| DEC-100 | [`spec/decisions/32-page-packer-reject.md`](spec/decisions/32-page-packer-reject.md) |

## 12. 交接判断

流程内核能指挥上层；业务侧当前停在 **Trunk、无活跃 POC**。
真正挡手的是 **Canvas 投影 stale**（所以 Product 只有打开文档），以及 **未提交 WIP + 卫生欠账**。

不要：把关闭 topic 当 exploring 继续修 binder；用 Harness 改本地 spec；
未 Refresh 就派 New Proposal / 委派 / 关题。

下一句人话应当是：Refresh snapshot，然后从 roadmap 或卫生里选**一条**开提案。
