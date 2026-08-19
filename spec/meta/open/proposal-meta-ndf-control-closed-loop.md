# Process 提案：NDF Control 白盒投影与可信闭环

> track: process
> Status: Implemented on 2026-08-17
> reviewed: 已审核
> control-flow: managed
> proposal-id: meta-ndf-control-closed-loop
> flow-id: meta-ndf-control-closed-loop
> 日期: 2026-08-17
> 修改: META-010, META-011, META-012, META-013；新增 META-014
> depends-on: META-001, META-002, META-008, META-010, META-011, META-012, META-013
> land-targets: spec/meta/process.md, spec/meta/README.md, AGENTS.md, spec/meta/tools/README.md, spec/meta/tools/ndf_context.py, spec/meta/tools/ndf_workflow_status.py, spec/meta/tools/ndf_replay.py, spec/meta/tools/test_ndf_context.py, spec/meta/tools/test_ndf_workflow_status.py, spec/meta/tools/test_ndf_replay.py, .cursor/skills/ndf-workflow-canvas/SKILL.md, .cursor/skills/ndf-workflow-canvas/actions.md, .cursor/skills/ndf-workflow-canvas/layout.md, .cursor/skills/ndf-workflow-canvas/snapshot-schema.md, .cursor/skills/ndf-workflow-canvas/openclaw-delegate.md
> 范围: NDF Control TAB / process proposal 生命周期 / project-control 信任链 / 白盒投影

## 1. 目的

NDF Control TAB 的首要目的，是将本地 NDF 规范内核与 NDF META workflow
**白盒可视化**，使用户能够以可核验的规则、依赖、状态和证据指导上层本地项目。
它不是第五 SoT，也不是隐藏式自动治理器。

页面的规范信息链 MUST 能回答：

```text
规范规则 → 当前证据 → 对本地项目的影响 → 责任人 → 有依据的下一步
```

每个摘要状态 MUST 可追溯到 clause、source path、content SHA、人工/工具回执或
verifier result。后端信任链与 fail-closed 机制服务于“显示可信”，MUST NOT 以增加
状态机复杂度取代用户可理解性。

## 2. 当前缺口

当前 `META-011`…`META-013` 已规定 Canvas 是派生投影、共享 Task Manifest、可写委派进入
Episode，并要求 OpenClaw request/response 可回放；但 project-control 的 process proposal
路径仍缺少一个完整的 L1 生命周期契约：

1. process proposal 的 `Draft / Implemented / reviewed` 主要由文件头自由文本推断，
   缺少稳定的 canonical machine state、合法前驱和终态定义。
2. 人类 `已确认` / `已审核` 与具体 proposal 内容束 SHA、actor、flow/hop 的绑定未形成
   独立契约；聊天确认、按钮回调与 Agent acknowledged 容易被混为同一事实。
3. `ndf_improvement_proposal` / `ndf_improvement_land` 已存在 pack 路径，但 intent /
   proposal identity、Manifest、request/response 与 mutation 的端到端对账仍不完整。
4. project-control Episode 不能稳定证明 `context.verified` 发生在 dispatch preflight 前，
   也不能完整区分 draft、confirm-land、review 三个权限不同的 hop。
5. 历史 process proposal 缺少现代回执时，当前投影可能把兼容文本状态误当作可操作状态，
   产生批量“待确认/待审核”或 false green。
6. freshness、health 与 action receipt 在规范、后端和 Canvas 中存在命名/消费差异；旧投影
   或未运行检查可能显示为 ready。
7. NDF Control 仍有只显示结论、不显示条款依据、证据来源和对 Product/Topics 影响的区域，
   未完全达到白盒指导目的。

## 3. 决策

### 3.1 新增 Process Proposal 生命周期契约

在 `spec/meta/process.md` 新增：

```markdown
## Process Proposal 生命周期与回执 {#META-014}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.16 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-010,META-011,META-012,META-013 -->
```

新托管 process proposal 的 canonical machine state MUST 为：

```text
pending_confirmation
→ confirmed_pending_land
→ implemented_pending_review
→ reviewed
```

`rejected` / `superseded` 为终态；archive 只是存储位置，不是生命周期状态。
旧 `Status: Implemented on ...`、`reviewed: 已审核` 只作为兼容输入，缺现代回执时 MUST
投影为 `legacy_*_unbound`，不得自动完成 gate 或产生可写 hop。

`proposal.confirmed` / `proposal.reviewed` MUST 由 human actor、精确口令、proposal
内容束 SHA、proposal ID、flow ID、hop 与时间组成 append-only 结构化回执。Agent/Canvas
acknowledged、按钮点击、Composer 对话创建或文件存在 MUST NOT 推进生命周期。绑定内容
漂移后，下游回执 MUST invalidated，不得改写历史。

### 3.2 分阶段权限与不可变 Episode

一个 `flow_id` MUST 使用三个权限不同、不可变的 child Episode：

| hop | MAY 写 | MUST NOT 写 |
|-----|--------|----------------|
| `draft` | 预先确定的单一 proposal 文件 | stable META、实现、审核回执 |
| `confirm_land` | 当前 proposal 与其中 Manifest 绑定的 `land-targets` | 未声明路径、审核回执、产品实现 |
| `review` | 当前 proposal 的 review marker / 绑定回执 | 重写已落地 META 或实现 |

每个 hop MUST 重新绑定当时的 intent/proposal/人口令 SHA、repo HEAD、Task Manifest 与
role plan。前一 hop 修改 proposal 或目标文件后，MUST 创建新的 child Episode /
Manifest；MUST NOT 在同一 Episode rebind 内容后继续执行。

`role × task × track × stage` MUST 机械校验。project-control 的实际 mutation MUST 与
声明的 stage 写入集合双向一致；越权、少报或多报均 fail closed。

### 3.3 Project-control dispatch 与幂等对账

project-control dispatch MUST 使用统一状态机：

```text
requested → pack_created → context_verified → sent
→ acknowledged | delivery_unknown | blocked
→ waiting_human | running | succeeded | failed
```

只有 verified Context Plan 才能产生 `dispatch.preflight`。发送请求与 OpenClaw 响应 MUST
绑定同一 `request_id`、Episode、Manifest、proposal/intent identity。timeout 进入
`delivery_unknown`，不得假装未发送或成功；重试 MUST 保持 request identity 并递增
attempt。匹配的迟到成功 MAY 进入 `acknowledged_late`；身份或结果冲突 MUST fail closed。

### 3.4 Freshness 与白盒投影

沿用 [[META-011]] 的 canonical freshness：

```text
fresh | refresh_in_progress | stale_after_action | unknown
```

其中 `fresh` 的含义是“当前 generation 已验证吸收最新终态 action”。只有 `fresh` 且相关
health/verifier 明确 `passed + current` 时，Canvas MAY 启用对应写动作。stale、not-run、
unknown、malformed action 或旧 kernel map MUST fail closed，不得显示为 ready/closed。

NDF Control 的每个主要区域 MUST 同时投影：

```text
applicable_clauses | dependency_edges | computed_state
evidence_refs | source_generation_sha | project_impact
owner | next_action
```

摘要状态必须可下钻；只给红黄绿、不提供推导依据不合格。Control finding 向上层项目的
handoff MUST 指明 Product/Topics scope、受影响规则、证据、owner 与安全动作；
MUST NOT 冒充产品 KPI 或替人类作产品决策。

### 3.5 平面路由与历史隔离

1. 产品 graph / proposal finding MUST 路由 Product；binder/topic finding MUST 路由
   Topics；META graph/index/process proposal 才路由 NDF Control。
2. `spec/meta/open/draft-map/**` 是已落地的既有 META 能力。它 MUST NOT 被扫描为
   process proposal/hop；其现行 warning 只读投影，Canvas MUST NOT 自动修改映射。
3. 历史 proposal 按兼容事实分类为
   `legacy_pending_unknown | legacy_implemented_unbound | legacy_reviewed_unbound |
   legacy_rejected_unbound | legacy_superseded_unbound`。
4. 历史 proposal 只有在人明确选择“纳入 Control flow”后，才 MAY 创建迁移 Episode；
   MUST NOT 批量伪造旧确认、旧审核或自动生成可写 hop。
5. `.openclaw/state.json` 只承载 workspace 绑定与 OpenClaw 指挥进度；MUST NOT 承载
   proposal/gate receipt、freshness、runtime lease 或 Replay 真值。

## 4. 实现范围

### 4.1 META 与文档

- 新增 [[META-014]]，并窄改 [[META-010]]…[[META-013]] 的 proposal receipt、
  project-control hop、freshness 与白盒投影衔接。
- 同步 `AGENTS.md`、`spec/meta/README.md`、`spec/meta/tools/README.md` 和 Canvas skill
  文档；不把 process 正文写回产品 `20-behavior/`。

### 4.2 后端

- `ndf_context.py`：Manifest 在 role-plan 前绑定 origin、intent SHA 或 proposal path /
  proposal SHA / hop；执行 stage compatibility 与内容漂移校验。
- `ndf_workflow_status.py`：实现 proposal lifecycle、project-control dispatch、late response
  对账、legacy quarantine、平面路由、canonical freshness 与白盒字段。
- `ndf_replay.py`：验证 draft/confirm-land/review child Episode 的 actor、identity、
  request/response、mutation 与 snapshot absorption。

### 4.3 NDF Control Canvas

保持主要因果链：

```text
Genesis → NDF 内核地图 → 自洽性/Advisor → 工作流演进 → 执行面卫生
```

每块统一使用“规则—证据—项目影响—下一步”解释结构。工作流演进展示真实
proposal/gate/dispatch/verification/replay 状态；前端 MUST NOT 从未知 status 文本自行
制造 hop，也 MUST NOT 把 Composer 创建成功显示成 OpenClaw 已接收。

Topics 已完成界面保持冻结；仅允许调整其消费的共享 schema/路由和必要 handoff，不重新设计
Topics UI。

## 5. 验收

1. 新建 process proposal 可按
   `draft → 已确认 → land → 已审核 → reviewed → snapshot absorbed` 完整回放。
2. 缺回执、错误 actor、proposal 漂移、stage 越权、timeout、迟到冲突、malformed action、
   stale snapshot、not-run health 与错平面 finding 均保持非绿色。
3. 同 request 的无冲突迟到响应可幂等对账，不重复创建批准或 mutation。
4. 历史 proposal 不自动产生可写 hop；显式迁移前只读展示 `legacy_*_unbound`。
5. NDF Control 每个主要状态可追溯到适用 META clause、source path、SHA 与证据；
   每个项目指导项包含 scope、impact、owner 与 next action。
6. greenfield `topics=[]`、accepted Genesis、混合 META/Product index、stale kernel map
   与失败恢复有前端 fixture。
7. `python3 spec/meta/tools/ndf_graphcheck.py --meta` hard_errors=0。
8. META 工具测试、Replay fsck、Canvas TypeScript/静态检查全部通过。
9. 最后一次 Canvas 更新使用官方 snapshot 原子嵌入，`--verify-embedded` 为 valid。

## 6. 不做

- 不重提或改变 Draft-map 已落地语义，不实现其条目生成器。
- 不修改 Trunk `src/` / `include/` / `tests/` 或产品 stable 契约。
- 不重新设计已完成的 Topics UI。
- 不回填或伪造历史 proposal 的人工确认/审核。
- 不把 Canvas、本地 UI history、`.openclaw/state.json` 或 Agent summary 变成新 SoT。
- 不在收到本提案「已确认」前修改 stable META、后端或 Canvas。

## Control receipts

| event | phrase | actor | at | proposal_sha | flow_id | hop | status |
|---|---|---|---|---|---|---|---|
| proposal.confirmed | 已确认 | human | 2026-08-17T15:00:00+03:00 | 9df136ce5c32c5c25d77b1284b24f635643218f057e9995c885813d401a0be9c | meta-ndf-control-closed-loop | confirm_land | valid |
| proposal.reviewed | 已审核 | human | 2026-08-17T16:48:00+03:00 | 9df136ce5c32c5c25d77b1284b24f635643218f057e9995c885813d401a0be9c | meta-ndf-control-closed-loop | review | valid |
