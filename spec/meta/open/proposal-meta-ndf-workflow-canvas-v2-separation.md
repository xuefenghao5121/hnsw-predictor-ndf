# Proposal: NDF Workflow Canvas 三平面分离 {#PROP-META-NDF-WORKFLOW-CANVAS-V2}

> track: process
> Status: Implemented on 2026-08-12
> 关联: [[META-008]], [[META-011]], [[DEF-NDF-WORKFLOW-PROJECTION]]
> 原则: 本地业务项目是主视图；Meta 是核心控制流；Agent runtime 是独立执行面

## 1. 问题

Canvas v1 将 Genesis maturity、process proposal、gate gap 和条款数量放在“Project”首页，
导致 `spec/meta/` 管控面被误读为业务项目本身。对本地产品而言，用户首先需要回答：

1. 产品目标与当前阶段是什么；
2. 哪些能力已稳定、哪些业务工作正在推进；
3. 当前 Golden/SLA/验证状态如何；
4. 哪些 NDF 控制问题或 Agent 运行问题阻塞业务推进。

## 2. 决策

Canvas 和 snapshot MUST 分离：

| 平面 | 回答 | 主数据源 |
|------|------|----------|
| Business Project | 本地产品要实现什么、正在推进什么、质量/性能如何 | `spec/00–50`、产品 `spec/open/`、产品 DEC、`src/`、POC、Golden |
| NDF Control | 是否满足可审计、安全推进条件 | `spec/meta/`、GATES、graph/bind/perf/isolation、Genesis |
| Agent Runtime | Claude Code 是否安全运行 | pipeline session/run/worktree/lease/completion |

1. 有产品 Charter 时，Canvas MUST 默认进入 Business Project。
2. Genesis maturity 只属于 Control；不得作为产品成熟度主 KPI。
3. 产品 proposal 与 process proposal MUST 分开扫描与展示。
4. Control/Runtime 问题 MAY 作为业务 blocker/badge 回传，但 MUST NOT 占据业务 KPI 主区。
5. Topic 详情仍按 Design/Implementation/Test 展示，但第一层信息 MUST 是业务假设、预期影响、
   当前证据；门禁和 Agent 状态为控制/执行补充。
6. close wizard MUST 标注每一步所属平面。
7. `pack`、`genesis-pack`、`close-plan` 的安全语义保持不变。

## 3. Snapshot v2

```text
business:
  identity / goals / capabilities / performance / roadmap
  product_proposals / topics / risks
control:
  genesis / process_proposals / spec_health / gate_summary
runtime:
  provider / status / active_runs / default_session
topics_detail:
  full orthogonal topic views
```

v1 `cockpit` 废弃。Canvas 快照仍是派生投影，不成为第四业务 SoT 或第五 NDF SoT。

## 4. Canvas 信息架构

默认标签：

```text
Product | Topics | Governance | Agents | Close
```

- Product：目标/阶段、能力组合、Performance vs Golden、业务工作、风险。
- Topics：业务假设/影响/证据优先的三空间工作台。
- Governance：Genesis、GATES、process proposals、规范健康。
- Agents：Claude Code runtime 与安全握手。
- Close：跨平面收口。

## 5. 产物

- `spec/meta/process.md`：[[META-011]] 三平面投影纪律薄修订；
- `spec/meta/tools/ndf_workflow_status.py`：snapshot v2；
- `.cursor/skills/ndf-workflow-canvas/`：Skill/layout/schema/Genesis 同步；
- workspace managed `ndf-workflow.canvas.tsx`：业务优先界面；
- `spec/meta/tools/README.md`：v2 使用说明。

## 6. 验收

1. 5 秒内可见产品名、Charter 目标、阶段、Golden 和 active business work；
2. Product 页无 process proposal、Meta clause count、Genesis warning 主 KPI；
3. 产品/process proposal 分类无混入；
4. 三个 exploring 业务 POC 可见假设、surface、证据与控制 blocker；
5. Control/Runtime 仍可阻断不安全派发；
6. snapshot 与 Canvas 数据一致；
7. meta/product graph hard errors = 0。

## 7. 非范围

- 改变 bootstrap、GATES、Claude Code 或 close-plan 语义；
- 将产品目标写进 `spec/meta/`；
- Canvas 直接写业务 SoT 或静默批准；
- 用 Harness 反推本地业务或 Meta。
