# Process 提案：NDF Workflow Canvas 可验证业务驾驶舱

> track: process
> Status: Implemented on 2026-08-12
> refines: META-011
> depends-on: META-008,META-009,META-010,META-011

## 背景

现有 Workflow Canvas 已分离 Business Project、NDF Control 与 Agent Runtime，并提供
Topics、Close Console 与 Agent 委派入口；但当前内嵌快照仍可能在连续操作后落后于
`spec/`、POC 装订器与 git。只提供手工 Refresh 不能证明界面已经吸收最新操作，容易把
过期投影误读为 ready、blocked 或 closed。

本提案将 Canvas 从“可浏览看板”收敛为可回答以下问题的业务驾驶舱：

1. 当前业务工作在哪里；
2. Design / Implementation / Test 是否分别就绪；
3. 下一合法步骤是什么；
4. 哪条 tree/git/tool 证据正在阻塞；
5. 当前投影是否覆盖了最近一次操作。

## 问题归类

| 问题 | 归属 | 处理 |
|------|------|------|
| Header 缺 Now / Next / Blocked | Canvas 呈现 | Canvas + snapshot 字段 |
| 三空间仅列 gaps、无 ready 聚合 | Canvas 呈现 | Canvas 读取 `topics_detail.spaces` |
| 风险卡片硬编码 | Canvas 呈现 | 改读 `business.risks` |
| 连续操作后 snapshot 漂移 | Canvas 投影 + Workflow 可观测性 | 可验证 action receipt 与 freshness |
| Genesis / DELTA / traceability 缺视图 | Canvas 呈现 | 使用已有/扩展 snapshot 投影 |
| Runtime 为 unavailable 常量 | 工具运行态投影 | 可选只读 probe；未知保持 unknown |
| Close promote/reject 未分轨 | Canvas 呈现 | 分支投影与严格 finalize 门禁 |

产品目标、POC gate、promote/reject 顺序与 `spec/` SoT 不因本提案改变。

## 变更

### 1. Snapshot 与 Canvas schema

`ndf_workflow_status.py snapshot` 与 Canvas 适配层 MUST 覆盖：

- `business.now_next_blocked`
- `business.risks`
- `control.genesis`
- `control.spec_health`
- `topics_detail[].spaces`
- `topics_detail[].binder/perf/agent_run/health`
- `control.close` 的 promote/reject 分支与 conservative evidence
- `projection_freshness`

工具 SHOULD 提供官方 Canvas JSON 格式，消除临时脚本对 snake_case / camelCase 的手工转换。

### 2. 可验证投影刷新

会改变本地 SoT 的 Canvas 发起操作 MUST 使用本地 append-only action receipt。回执是
运行审计证据，不是产品或 process SoT；默认落在 gitignored 的
`tmp/ndf-workflow-actions.jsonl`。

每条终态回执至少包含：

```text
action_id | topic | operation | started_at | finished_at | result
repo_head_before | repo_head_after | snapshot_sha_after | blockers
```

状态工具 MUST 从回执与当前 tree/git 计算：

```text
fresh | refresh_in_progress | stale_after_action | unknown
```

- `fresh`：投影绑定的 repo/tree generation 覆盖最新终态 action；
- `refresh_in_progress`：存在已开始但未终结的 action；
- `stale_after_action`：最新终态 action 尚未被当前 Canvas snapshot 吸收；
- `unknown`：无法取得可验证操作证据。

Canvas dispatch MAY 先用本地 UI state 标记 `refresh_in_progress`，但 MUST 以工具投影为最终
判定。每个 action 的 Composer prompt MUST 执行 begin/finish receipt，并在成功或失败后
生成新 snapshot、更新整个 Canvas。若平台无法自动重载，Canvas MUST 显示 stale banner，
不得把手工 Refresh 当成已同步证明。

### 3. 业务与三空间视图

- 全局 Header MUST 展示 Now / Next / Blocked，以及 snapshot SHA、最新 action SHA 与 freshness。
- Product risks MUST 来自 `business.risks`；无数据时省略。
- Topic 三列 MUST 展示独立 `ready/not-ready` 与 gaps；Numbers pending、baseline stale、
  gate `legacy_unknown|invalidated` 时 MUST NOT 显示绿色 ready。
- Topics SHOULD 展示 DELTA Feature→Hotspot→latest Round 与
  goal/clause→design→code/commit→verification traceability。

### 4. Governance、Runtime 与 Close

- Governance MUST 展示 Genesis G0 IDEA → G1 Foundation → G2 Trunk Candidate → G3 Freeze；
  健康棕地 `operational_legacy` 不阻断日常工作。
- Agents MAY 提供显式只读 runtime probe；未探测或失败 MUST 显示 `unavailable|unknown`，
  不得推断 idle。
- Close MUST 分开展示 promote、partial 与 reject 路径；finalize 只有在对应路径所有 required
  evidence 为 green 时才可用。未知 graph/build/perf/golden 继续显示 pending。

### 5. 操作入口

Canvas actions 与 action catalog 对齐：

- New Proposal / New Genesis
- Prepare POC pack / Delegate POC
- Perf bind / POC isolation
- Control delegation
- Close plan / promote/reject operation

所有写操作继续通过 Composer、OpenClaw 或 Claude Code 执行；Canvas MUST NOT 直接批准
人工门禁或绕过 proposal、close-plan、verification。

## 写入范围

- `spec/meta/process.md`：amend [[META-011]] 的 freshness/action receipt 边界
- `spec/meta/tools/ndf_workflow_status.py` 与工具文档/测试
- `.cursor/skills/ndf-workflow-canvas/`
- workspace managed `canvases/ndf-workflow.canvas.tsx`
- 本提案状态

不修改产品 `spec/00–50`、Trunk `src/`、`include/`、`tests/` 或性能 Golden。

## 验收

1. 连续执行两个 Canvas action 后，旧 Canvas 必须显示
   `refresh_in_progress|stale_after_action`，不得静默保持 fresh。
2. action 成功与失败都生成终态 receipt；刷新后 snapshot 覆盖最新 action。
3. Header、三空间、风险、Genesis、DELTA/traceability、Close 分支均来自 snapshot，
   不依赖硬编码业务状态。
4. 未探测 runtime、未知 verification、legacy gate 不显示为 ready。
5. `ndf_graphcheck.py --meta` hard errors 为 0，Canvas TypeScript 检查无错误。

## 非目标

- 将 Canvas 或 action receipt 提升为第五 SoT；
- Canvas 内嵌实时 Agent chat；
- 自动批准人工 gate；
- 通过 runtime probe 修改 Agent 或项目状态；
- 修改产品行为、SLA 或 Trunk 实现。
