# Proposal: NDF Workflow Canvas 与 Project Genesis {#PROP-META-NDF-WORKFLOW-CANVAS}

> track: process  
> Status: Implemented on 2026-08-12  
> 日期: 2026-08-12  
> 关联: [[META-003]], [[META-008]], [[BEH-018]], [[BEH-019]], [[BEH-025]]  
> 原则: Canvas 只投影真值并编排动作；Project Genesis 先建立本地 NDF 与初始 Trunk，
> 日常 Proposal/POC 再沿三工作空间闭环

## 1. 动机

现行工作流从「本地 NDF 已完整的健康棕地」开始，能管理 Proposal → POC →
promote/reject，但缺少：

1. 原始 IDEA、项目目标与非目标的可审计金标化；
2. greenfield 或已有代码接管时，初始本地 `spec/00–50` 的建立流程；
3. 初始 Trunk candidate 如何在人工门禁后由 Claude Code 沙箱建立并验证；
4. 人工门禁回执、Agent 运行状态与三工作空间 readiness 的可信可视化；
5. POC 关闭时，NDF 文档与代码按严格顺序回合主线的管理界面。

若 Canvas 只展示概念图，或凭文件存在猜测审批状态，会形成影子 SoT。若把
`poc/<topic>/` 路径约束称为沙箱，也会掩盖真实执行隔离缺失。

## 2. 决策

### 2.1 新增一次性 `track=bootstrap`

在日常 track 之前增加 Project Genesis 初始化轨：

```text
> track: bootstrap
> bootstrap_mode: greenfield | adopt
```

- `greenfield`：从原始 IDEA 建立 Charter、初始 NDF Foundation 与初始 Trunk；
- `adopt`：对已有代码做 observed 盘点、建立本地 NDF、验证并冻结 Genesis；
- accepted Genesis 已存在时 MUST NOT 重跑 bootstrap；重建基准另开 process/refactor 提案；
- bootstrap 完成前，普通 Proposal/POC 默认禁用；初始化期未知方向 MAY 显式开 research POC。

项目成熟度与 POC lifecycle 正交：

```text
uninitialized → idea_review → ndf_foundation
→ trunk_candidate → validating → operational
```

### 2.2 原始 IDEA 与项目目标金标

初始化 MUST 保留用户原始 IDEA，并分段审核：

```text
IDEA已审核
→ CHARTER已审核
→ ARCHITECTURE已审核
→ VERIFICATION已审核
→ 可以建立初始主线
→ GENESIS已审核
```

最终「项目目标金标」由以下三者共同绑定：

1. `spec/00-charter/`：确认后的目标、scope、non-goals；
2. `spec/decisions/dec-project-genesis.md`：原始 IDEA 来源、取舍、已知 draft；
3. Genesis NDF tree SHA + Trunk SHA + verification reference。

项目目标金标与性能 Golden Baseline MUST 区分。没有合格性能证据时，性能金标为
`not-established`，MUST NOT 造数或把 aspiration 写成 stable SLA。

### 2.3 初始 Trunk 建立

收到「可以建立初始主线」后：

1. 生成绑定已审核 Foundation 内容 SHA 的 bootstrap context pack；
2. 通过已绑定 Claude Code 管道启动独立 worktree/branch；
3. Claude Code 可写初始 `src/`、`include/`、`tests/`、构建配置与 L2/L3；
4. Claude Code MUST NOT 修改 L0/L1、Charter、Architecture、Decisions、`spec/meta/`；
5. greenfield 先建立最小可构建垂直切片；未知机制转后续 POC；
6. adopt 不改写旧 git 历史，只建立 observed NDF、验证与 Genesis 绑定；
7. build、最低功能验收、index、graphcheck 与三空间追踪全部闭合后，才可
   `GENESIS已审核` 并进入 `operational`。

### 2.4 四个 P0 安全修订

#### P0-1：真实沙箱

Claude Code 管道 MUST 返回 `run_id/session_id`、`base_sha`、独立
`worktree/branch`（或可证明等价隔离）与 `allowed_write_root`。NDF 写入路径纪律是第二层；
任一层缺失，Canvas MUST 显示 `unsafe` 并拒绝派发。同一 topic 同时至多一个写 run。

#### P0-2：可审计门禁

Canvas-managed POC 增加 `poc/<topic>/ndf/GATES.md`；Genesis 使用对应初始化回执文件。
回执 MUST 至少记录：

```text
gate / phrase / approved_by / approved_at
approved_content_sha / source_ref / status
```

文件存在 MUST NOT 推导为已审核。审批绑定内容实质变化时，下游回执 MUST 追加
`invalidated`，不得改写历史回执。

#### P0-3：正交状态

Canvas 快照 MUST 分开投影：

- `project_maturity`
- `lifecycle`
- `gates`
- `spaces.design|implementation|test`
- `agent_run`
- `health.blockers|conflicts|stale`

`phase_hint` 仅作 UI 导航，不落盘、不成为流程真值。partial promote 后 topic 仍为
`exploring`。

#### P0-4：严格关闭顺序

正结果：

```text
POC evidence ready
→ promote proposal 已确认并落地
→ promote proposal 已审核
→ ndf_close plan
→ Claude Code 主线集成
→ index/graphcheck
→ 编译/性能/金标验证
→ TOPIC/COMMITS/NOTES/归档最终收口
```

全部验证完成前只能显示 `closing`。reject 使用 DEC/deprecated/归档分支，不经过
promote 集成。Canvas 工具只提供只读 `close-plan`，不提供静默 apply。

### 2.5 Canvas 信息架构

Canvas 分为：

| 界面 | 回答 |
|------|------|
| Genesis G0 IDEA | 原始想法与 Agent 推断如何区分 |
| Genesis G1 Foundation | 初始 Design/Test 契约是否足以指导代码 |
| Genesis G2 Trunk Candidate | Claude Code 基于哪个 SHA、建立哪个最小切片 |
| Genesis G3 Freeze | NDF、代码、验证是否绑定到同一 Genesis |
| 项目驾驶舱 | Now / Next / Blocked；活跃 Proposal/POC 与三空间缺口 |
| 主题工作台 | Design / Implementation / Test + DELTA + gate receipts |
| 关闭向导 | promote/reject 提案、close plan、主线验证与最终收口 |

Canvas 是 [[META-008]] 交互编排的投影，不是第五 SoT。

## 3. 条款与产物计划

### 3.1 拟新增 process 条款

| ID | 主题 | 结构依赖 |
|----|------|----------|
| `META-009` | Project Genesis / `track=bootstrap` | `META-003,META-008` |
| `META-010` | 人工门禁回执与内容 SHA | `META-001,META-008` |
| `META-011` | Workflow projection 与 Claude Code 沙箱委派 | `META-008,META-010` |

新条款正文只写产品无关流程；MUST NOT 结构依赖产品条款。

### 3.2 拟新增/修改文件

- `spec/meta/process.md`：META-009…011、BEH-025 的 `GATES.md` 装订指针；
- `spec/meta/templates/genesis/`：IDEA、Genesis DEC、Foundation matrix、GATES；
- `spec/meta/templates/poc/GATES.md.stub`；
- `spec/meta/tools/ndf_workflow_status.py`：
  `genesis-status` / `genesis-pack` / `snapshot` / `pack` / `close-plan`；
- `.cursor/skills/ndf-workflow-canvas/`：
  `SKILL.md`、`genesis.md`、`layout.md`、Claude Code 委派/管道契约；
- `AGENTS.md`、`poc/README.md`、`spec/meta/README.md`、`spec/meta/tools/README.md`、
  `spec/meta/tools/GOVERNANCE.md` 薄同步。

本案不修改 `.openclaw/state.json`，不修改 Trunk 产品代码，不蒸馏
`packages/ndf-harness/`。

## 4. 实施分段

1. **MVP-0**：Genesis Center、greenfield/adopt 模板、项目成熟度检测；
2. **MVP-A**：GATES 回执、正交 snapshot、项目/主题 Canvas；
3. **MVP-B**：Claude Code 管道握手、pack、lease、完成回执；
4. **MVP-C**：只读 close-plan 与严格 promote/reject 关闭向导。

## 5. 验收

1. mock greenfield：IDEA → Foundation gates → Trunk candidate → build/test →
   Genesis DEC/SHA → operational；
2. mock adopt：已有代码 → observed NDF → build/baseline → Genesis 绑定，旧历史不改写；
3. mock POC：Proposal → binder gates → Claude Code 沙箱 → evidence → close-plan；
4. 改写已审核内容后，相关 gate 显示 invalidated，Agent 不得启动；
5. 管道缺 `base_sha/worktree/run_id` 时显示 unsafe；
6. partial、Agent failed、baseline stale 可同时正确表达；
7. `python3 spec/meta/tools/ndf_graphcheck.py --meta`：`hard_errors=0`。

## 6. 非范围

- Canvas 直接代替人工口令或静默批准；
- bootstrap 一次性生成完整臆想系统；
- 自动修改 stable 条款、自动 merge Trunk、`ndf_close apply`；
- 将 Canvas 快照或 Agent 运行态当作产品/流程 must；
- 回填既有 POC 的 GATES 历史；
- 用 Harness 内容反推或纠正本地 `spec/meta/`。
