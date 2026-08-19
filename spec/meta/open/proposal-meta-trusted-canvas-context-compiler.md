# Process 提案：NDF 可信控制与上下文编译

> track: process
> Status: Implemented on 2026-08-12
> 日期: 2026-08-12
> 新增: META-012
> refines: META-011
> 关联: [[META-002]], [[META-008]], [[META-010]], [[META-011]], [[BEH-025]]
> 范围: Workflow evidence / Context Compiler / Agent packs / Canvas / Close

## 1. 背景

当前 Workflow Canvas 已能分离 Business Project、NDF Control 与 Agent Runtime，
并按 Design / Implementation / Test 展示 topic health；但深度审核发现两类根本缺口：

1. **控制可信性不足**：projection `fresh` 未绑定实际嵌入 Canvas payload；
   Golden `current` 未校验当前 HEAD；Close 可接受 NOTES-only 或无绑定 `tmp` 报告；
   静态 pack preflight 未与 runtime lease 分离。
2. **上下文不一致**：Canvas 展示一个工作空间，而 OpenClaw / Claude Code pack
   仍使用固定文件列表；未按 `AGENTS.md` 的
   `binder → NDF graph → git/evidence` 顺序机械生成真实任务上下文。

因此现有面板适合作为派生看板，但不足以作为可信的 Agent 控制面。

## 2. 决策

新增 [[META-012]]「NDF 任务上下文与证据绑定」，并薄修 [[META-011]]。

统一任务上下文定义为：

```text
RealTaskContext
= BinderReadOrder
+ NDFGraphClosure
+ Git/ImplementationSurface
+ Evidence/Baseline
+ Gate/RuntimeLease
+ RoleSpecificPrivilege
```

Canvas、OpenClaw 与 Claude Code MUST 消费同一个带 SHA 的 Context Plan；
Canvas 只展示摘要，不维护第二套上下文拼接。

所有可使状态变绿或允许写入的结论 MUST 来自绑定 topic / mode / task /
repo HEAD / source generation / input-output SHA 的 receipt。旧无绑定 artifact
只能显示 `legacy_unbound`，MUST NOT 完成 gate、Close 或 dispatch readiness。

## 3. [[META-012]] 拟定契约

### 3.1 Context 编译顺序

Context Compiler MUST：

1. 先按 [[BEH-025]] 装订器读序：

   ```text
   TOPIC → DESIGN → PERF_BASELINE → DELTA → INTERFACE
   → GATES → proposals → evidence → COMMITS
   ```

2. 从 TOPIC、proposal、COMMITS/trailer、task 默认条款与 close plan 提取 clause seeds；
3. 按 task/role 策略展开 NDF 图；
4. 纳入 repo HEAD、baseline、gate bundle、ledger、perf bind 与 evidence；
5. 施加角色化读写权限与内容预算；
6. 生成 canonical plan SHA / bundle SHA，并在 dispatch 前重新 verify。

### 3.2 图策略

- 默认只沿 `depends-on` / `refines` 展开；
- Test/verify MAY 纳入 `verifies`；
- Promote impact MAY 纳入 `affects` / `couples-with` 一跳；
- `conflicts-with` 产生 blocker，不自动扩展；
- `model` 仅在 promote / semantic-core 任务启用；
- wiki 引用 MUST NOT 冒充图边；
- deprecated 非 seed 节点 SHOULD 沿 `superseded-by` 重定向；
- process task MUST 使用 meta-only 图，禁止 process→product 结构依赖；
- traversal MUST 有 depth/node/byte budget，截断 MUST 显式报告。

### 3.3 角色切片

| role | 上下文 | 禁止 |
|---|---|---|
| Canvas / human | 路径、标题、摘要、图切片、缺口 | 全量预载 spec |
| OpenClaw | L0/L1、binder、gate、proposal、图缺陷/影响面 | 产品代码实现 |
| Claude Code POC | 已批准 L1、topic code、VER/perf/evidence、POC 写根 | Trunk / meta / stable SLA |
| Claude Code promote | reviewed proposal、close plan、stable contract/VER/model、Trunk surface | L0/L1/meta |
| Project Control | meta-only graph、spec-health、process proposal | 产品实现 |

### 3.4 静态与运行态

MUST 区分：

```text
static_preflight_passed
runtime_dispatch_ready
```

- static：gate、baseline、perf、isolation、context verify；
- runtime：pipeline reachable、无同 topic lease、run/session/base/worktree/root 握手完整。

缺 runtime adapter 时 MUST 显示 `unavailable`，不得声称 safe。

## 4. Evidence 与 freshness

新增共享 evidence 原语及 schema：

- `ndf-projection-receipt/v2`
- `ndf-close-evidence/v1`
- `ndf-runtime-lease/v1`

每个 receipt 至少绑定：

```text
schema / task / topic / mode / step
repo_head / source_generation_sha / context_plan_sha
command / input_sha / output_sha / evidence_paths
started_at / finished_at / result / blockers
```

projection MUST 分离：

- `evidence_generation`：snapshot 生成时的树/图/git generation；
- `embedded_projection`：managed Canvas 是否吸收指定 action/payload。

`action-finish` 只证明 operation 结束，MUST NOT 单独宣称 Canvas fresh。
工具 SHOULD 提供 `snapshot --verify-embedded <canvas>`。

## 5. Golden / Gate / Workspace / Runtime

1. Golden status MUST 比较现行 Golden SHA 与当前 HEAD，区分：
   `aligned | head_ahead_of_golden | golden_unresolvable | missing`。
2. Gate MUST 投影 expected 与 recorded 完整 SHA；旧短 SHA 为 `legacy_weak`，
   不得用于自动委派。
3. `state_file_exists` MUST NOT 等价于 `workspace_bound`；必须比较 persisted
   repo_root / HEAD / active topic。
4. Runtime lease 仅写 gitignored `tmp/ndf-workflow-leases.jsonl`，不写
   `.openclaw/state.json` 冒充运行态。

## 6. Close 可信性

Close MUST 按 mode 使用独立证据：

- promote/partial：binder 最低闭合、perf bind、Numbers、DELTA/evidence；
- reject：Rejects DEC/proposal、根因、代码 disposition；
- graph/build/perf/golden 只接受 `ndf-close-evidence/v1`；
- receipt 必须匹配 topic、mode、HEAD、generation 与 evidence SHA；
- NOTES-only、旧裸 `tmp`、`Implemented` 字样 MUST NOT 使步骤变绿；
- partial MUST NOT 复用 full promote proposal；
- 全部验证前显示 `closing`，不得提前 finalized。

## 7. 产物

确认后依次落地：

1. `spec/meta/process.md`：新增 [[META-012]]，薄修 [[META-011]]；
2. `AGENTS.md` / `spec/meta/README.md`：增加 META-012 指针与机械 context 命令；
3. `spec/meta/tools/ndf_workflow_evidence.py`：canonical hash / receipts / workspace truth；
4. `spec/meta/tools/ndf_context.py`：
   `context-plan` / `context-expand` / `context-verify`；
5. `ndf_workflow_status.py`：pack v2、静态/runtime readiness、Golden/Gate/Close 修复；
6. Workflow Canvas：Context Preview、receipt/finding diff、统一导航与 topic；
7. Canvas Skill / tools README / schema 文档；
8. context/workflow 负例与集成测试。

## 8. 兼容与边界

- pack/schema v2 采用 additive migration；v1 保留一个周期并标 `legacy_context`；
- 旧 action/gate/close artifact 不删除，只降级为 `legacy_unbound`；
- 不改写 git 历史；
- 不动产品 `src/`、SLA 或 POC 实现；
- Cursor/Canvas/context 工具 MUST NOT 修改 `.openclaw/state.json`；
- 不使用或同步 `packages/ndf-harness/` 反推本地 SoT；本地验证后另案提炼。

## 9. 验收

1. 同一 task 的 Canvas Context Preview、OpenClaw pack、Claude pack 共享相同 plan SHA；
2. binder-first、图闭包、git/evidence join、角色权限可机械验证；
3. graph depth/budget/plane 边界与 Numbers 防泄漏负例通过；
4. 未吸收 action 的旧 Canvas 不得显示 verified；
5. HEAD 与 Golden 不一致不得显示 current/success；
6. 短 gate SHA、state file-only、active lease 均正确阻断或降级；
7. NOTES-only、伪造/旧 Close tmp、错误 mode proposal 均不得完成 Close；
8. repair 前后显示 Resolved / Remaining / New findings，并绑定 action/context SHA；
9. `.openclaw/state.json` 无 Cursor 侧改动；
10. `ndf_graphcheck.py --meta` hard_errors=0，Python context/workflow 测试、
    Canvas TypeScript 与 bundle 全部通过。
