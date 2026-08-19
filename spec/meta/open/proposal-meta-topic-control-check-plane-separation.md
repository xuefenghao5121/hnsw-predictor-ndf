# Process 提案：Business Topic 与 NDF Control 检查分面

> track: process
> Status: Implemented on 2026-08-13
> 日期: 2026-08-13
> 修改: META-011
> depends-on: META-008, META-011, META-012
> 范围: workflow snapshot / topic health / Canvas Topics / Governance

## 1. 问题

当前 Canvas 的 Business Topic 详情把 `topic.health.checks` 原样展开，其中包含：

```text
perf_baseline
isolation
bindcheck
```

以 `cluster-gbdt` 为例，Topic 本身是产品探索：其 `TOPIC.md` 指向 learned-pruning、
GBDT 特征与性能基线；但 `isolation` 和 `bindcheck` 是 [[META-011]] 定义的 NDF Control
治理检查。把三者放入同一 “Topic health checks” 表，会造成：

1. 将流程治理工具误读为产品行为或业务 KPI；
2. Business Topic 与 NDF Control 的 owner/action 混杂；
3. “检查通过”被误读为业务空间 ready；
4. 用户无法判断问题应由业务实现、OpenClaw Control 还是工具治理处理。

这不是 `cluster-gbdt` 的 topic 分类错误，而是检查结果的展示平面错误。

## 2. 决策

对齐 [[META-008]]、[[META-011]]，工作流投影 MUST 将 Topic 数据拆为：

```text
business_topic
  ├─ business evidence / hypothesis / expected impact
  ├─ Design / Implementation / Test readiness
  └─ control blocker summary（badge/pointer only）

ndf_control.topic_governance
  ├─ gate receipt audit
  ├─ bindcheck
  ├─ POC isolation
  ├─ context/dispatch preflight
  └─ repair owner / task / evidence
```

Business Topic 页面不得展开 NDF Control 工具原始报告。Control 失败 MAY 阻止
Implementation ready 或 dispatch，但必须以明确的 `control_blocker` badge/pointer 回传，
并链接到 Governance/NDF Control 视图。

## 3. 检查归属

| 检查 | 权威平面 | Business Topic 呈现 |
|---|---|---|
| `perf_baseline` 的 Numbers、baseline status、protocol 与 DELTA 状态 | Test space | 业务 Test readiness / gaps |
| `ndf_poc_isolation` | NDF Control | `isolation_blocked|passed` badge；不展开报告 |
| `ndf_bindcheck` | NDF Control | `binding_blocked|passed` badge；不展开报告 |
| gate receipt SHA / legacy / invalidated | NDF Control | 当前 gate 状态与下一人工口令 |
| context verify / writable preflight | NDF Control + Agent Runtime | dispatch badge/blocker |
| 产品结果、性能数字、业务 evidence | Business Project | 正常展开 |

`perf_baseline` 工具实现属于 meta harness，但其产品测量状态投影到 Test space；工具命令、
parser 与治理诊断仍属于 Control。界面必须区分“业务结果”与“治理执行细节”。

## 4. Snapshot 调整

`ndf_workflow_status.py` SHOULD 将 topic detail 拆为：

```json
{
  "business_health": {
    "spaces": {},
    "test_status": {},
    "business_findings": []
  },
  "control_health": {
    "checks": {},
    "findings": [],
    "next_actions": [],
    "diagnosis_freshness": {}
  },
  "control_summary": {
    "blocked": true,
    "badges": [],
    "governance_topic_ref": "cluster-gbdt"
  }
}
```

兼容期 MAY 保留旧 `health` 字段，但 Canvas MUST 优先消费新分面；旧字段必须标
`deprecated_projection`，不得继续作为 Business Topic 原始检查表。

`safe_to_dispatch` 仍必须使用 isolation/bind/context/gate 结果 fail closed；本提案只改变
平面和呈现，不削弱委派门禁。

## 5. Canvas 调整

### Topics

Business Topic 详情保留：

- hypothesis / expected impact / business evidence；
- Design / Implementation / Test readiness；
- baseline、Numbers、DELTA、traceability；
- gate 状态与下一人工口令；
- `NDF Control blockers` 汇总 badge。

删除或迁出当前原始 `Topic health checks` 表中的 `isolation`、`bindcheck` 命令与长报告。
Control badge 点击后切换到 Governance，并保留 topic filter。

### Governance / NDF Control

新增 topic-scoped governance 区：

- topic selector；
- gate receipt、bindcheck、isolation、context/preflight；
- diagnosis freshness；
- structured findings、repair owner/task、allowed root、human gate；
- inspect → repair → refresh 动作。

通过状态必须描述为“control check passed”，不得描述为业务成功。

## 6. 验收

1. `cluster-gbdt` 仍出现在 Business Topics，因为它是产品 POC；
2. Business Topic 页面不再展开 `ndf_poc_isolation` / `ndf_bindcheck` 原始报告；
3. isolation/bindcheck 失败仍使 dispatch fail closed，并显示 Control blocker badge；
4. Governance 能按 topic 展示完整检查、evidence、owner 与 repair action；
5. `perf_baseline` 业务状态留在 Test space，工具执行细节进入 Control；
6. proposal plane、Business/Control/Runtime 三平面保持正交；
7. snapshot schema、Python tests、Canvas TypeScript 检查通过；
8. `.openclaw/state.json` 不被修改。

## 7. 实施范围

- `spec/meta/process.md`：补充 [[META-011]] topic-scoped Control 分面规则；
- `spec/meta/tools/ndf_workflow_status.py`：拆分 business/control health projection；
- `spec/meta/tools/test_ndf_workflow_status.py`：新增平面归属与 fail-closed 测试；
- `.cursor/skills/ndf-workflow-canvas/`：更新 schema/layout/actions；
- Canvas TSX：迁移 raw checks 到 Governance topic filter；
- 刷新 embedded snapshot 并验证 projection receipt。

## 8. 边界

- 不把产品 POC 从 Business Topics 删除；
- 不降低 isolation、bindcheck、gate 或 context dispatch 门禁；
- 不修改产品 `src/`、`include/`、`tests/`；
- 不修改 `.openclaw/state.json`；
- 本提案确认前不修改 [[META-011]] 正文、projection 或 Canvas。
