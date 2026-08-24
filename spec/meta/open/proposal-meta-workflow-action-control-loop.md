# Process 提案：NDF 工作流动作闭环

> track: process
> Status: Implemented on 2026-08-12
> 日期: 2026-08-12
> refines: META-011
> 关联: [[META-008]], [[META-010]], [[META-011]], [[BEH-025]]
> 范围: Workflow snapshot / Canvas Topics / Governance / Agent 路由

## 1. 问题

Workflow snapshot 已将 lifecycle、gates、Design / Implementation / Test、agent runtime
与 health 正交投影，但 Topics 动作层仍是按钮集合：

1. `Run topic health check` 已包含 gate SHA、perf bind、isolation 与 pack preflight，
   却又分别暴露这些按钮；
2. `Prepare POC pack` 与 `Delegate POC` 混淆只读 preflight 和实际实现委派；
3. `Audit legacy gates`、`Check gate SHA`、`Prepare gate draft` 与泛化的
   `Delegate to OpenClaw` 缺少阶段化关系，当前阶段还会出现等价动作；
4. 检查完成后只在 Composer 输出摘要，没有结构化 finding、修复责任人、允许写根与复检；
5. Governance 偏重单 topic gate，未完整呈现项目级 NDF 图、绑定、索引与流程符合性；
6. `safe_to_dispatch` 尚未把完整 perf baseline 与 POC isolation 检查纳入统一 preflight。

结果是：数据面接近正交，操作面却不正交；人需要自行记忆工具依赖与 Agent 边界。

## 2. 决策

Canvas 动作 MUST 按以下四轴路由：

```text
scope(project|topic|close)
× space(Design|Implementation|Test)
× stage(inspect|repair|refresh)
× owner(tool|OpenClaw|Claude Code|human)
```

标准闭环为：

```text
inspect → structured findings → owner/task routing
→ bounded repair or human gate → recheck → refresh
```

`dispatched` MUST NOT 等价于 `repaired` 或 `completed`。修复结果 MUST 由文件、git、
工具报告或运行回执重新证明；Canvas 只投影证据。

## 3. Topic 动作模型

### 3.1 Inspect

`topic-health --topic <id>` MUST 统一检查：

- gate receipt / bundle SHA；
- 完整 PERF_BASELINE 绑定；
- POC isolation；
- topic bindcheck；
- implementation pack preflight。

每条 finding 至少输出：

```text
scope | space | kind | severity | evidence
repair_owner | repair_task | allowed_write_root | human_gate
```

### 3.2 Repair owner

| Finding | 修复责任 |
|---|---|
| Design / gate / binder / PERF 绑定头 | OpenClaw：audit / binder_amend / control_proposal |
| POC code / isolation / Numbers / evidence / DELTA rounds | Claude Code：仅允许写根内修复 |
| gate phrase / proposal 确认审核 | Human |
| project graph / process defect | Advisor 诊断 → process proposal → Human |

Perf bind 的职责 MUST 分开：工具只读检查；OpenClaw 修绑定头与装订器叙述；
Claude Code 运行测量并填写 Numbers / evidence。Isolation 工具只读检查；
Claude Code 修 POC 写入面，破坏性 git 修复仍需人工决策。

### 3.3 Canvas

Topics 主动作收敛为：

1. `Refresh topic`：仅刷新派生投影；
2. `Diagnose topic`：运行统一检查并显示三空间 findings；
3. `Repair with OpenClaw` / `Repair with Claude Code`：仅在 finding 给出明确 task 时显示；
4. `Delegate POC`：仅统一 preflight 全绿时启用；
5. `Open business topic`：保留人工查看入口。

pack、perf check、isolation check 不再作为平级主按钮。Topic NDF Control 只显示一个
带具体任务名的下一步，不显示含义不明的泛化 `Delegate to OpenClaw`。

人工口令仍为 `TOPIC已审核` → `DESIGN已审核` → `可以开始实现`；Canvas / Agent
MUST NOT 写入或伪造 `approved_by`。

## 4. Project NDF Control

Governance MUST 监测项目级 NDF 工作流符合性：

- meta graph；
- product graph；
- index consistency；
- all-topic binder health；
- gate summary；
- proposal hygiene。

`spec-health` MUST 返回结构化 checks / findings / next actions。检查报告仅写
gitignored `tmp/`；工具 MUST NOT 静默修改 SoT。

Governance MAY 提供：

- `Run NDF Control check`；
- Advisor 只读诊断入口；
- `Start NDF improvement proposal`；
- 有明确 task 的 OpenClaw 专项修复。

Governance MUST NOT 把产品 POC 实现任务委派给 OpenClaw。产品实现继续通过
Topics / Close 路由到 Claude Code。

## 5. 委派安全

POC `safe_to_dispatch` MUST 同时要求：

1. implementation approval 回执有效；
2. baseline 非 stale；
3. 完整 PERF_BASELINE 检查无 error；
4. POC isolation preflight 无 error；
5. Claude Code handshake / lease 条件仍按 [[META-011]] 校验。

任何检查未知、过期或失败时 MUST 阻止 `Delegate POC`，不得以轻量 header parse
或按钮点击推断安全。

## 6. 状态与写入边界

- action receipt / health report / advisor report 仅写 `tmp/`，不是 SoT；
- Cursor、Canvas 与 `ndf_workflow_status.py` MUST NOT 修改 `.openclaw/state.json`；
- OpenClaw 仅在收到明确 control-pack 后按既有 workspace 绑定纪律处理自己的工作状态；
- OpenClaw MUST NOT 修改稳定 `spec/meta/` 正文；本提案确认后的 META-011 落地由指挥层执行；
- Claude Code MUST NOT 修改 `spec/meta/`、L0/L1 或 POC 允许写根之外路径；
- 工具 MUST NOT 自动批准 gate、改 git 历史或把 POC 数字写入 stable SLA。

## 7. 产物

确认后落地：

1. `spec/meta/process.md`：[[META-011]] 增补 inspect / repair / refresh 与 finding owner；
2. `spec/meta/tools/ndf_workflow_status.py`：`topic-health`、`spec-health`、结构化路由、
   严格 pack preflight；
3. managed `ndf-workflow.canvas.tsx`：Topics 动作收敛与 Governance conformance；
4. `.cursor/skills/ndf-workflow-canvas/` 与 `spec/meta/tools/README.md`；
5. workflow status 工具测试。

## 8. 验收

1. Topics 不再出现重复 pack / perf / isolation / OpenClaw 平级按钮；
2. 每个 finding 能回答空间、证据、修复 owner、task、允许写根与复检方法；
3. perf 绑定头问题路由 OpenClaw；Numbers / evidence 路由 Claude Code；
4. isolation 失败或未知时 `Delegate POC` 不可用；
5. Governance 显示项目级 graph / bind / index / workflow conformance；
6. OpenClaw 委派必须显示具体 task，产品实现不得进入 OpenClaw；
7. repair 后 action receipt + 复检 + 官方 snapshot 闭环；
8. `.openclaw/state.json` 无 Cursor 侧改动；
9. `ndf_graphcheck.py --meta` hard_errors=0，Python 测试与 Canvas TypeScript 构建通过。
