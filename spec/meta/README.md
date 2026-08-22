# NDF Process Profile（本仓元规范）

> **role:** ndf-process-profile
> **product_behavior:** false
> **sot:** true（对本仓 Agent **流程纪律**）；**false**（对 DiskHNSW **检索/缓存/SLA 产品行为**）

本目录是仓库对 NDF 的 **process profile**：探索/晋升双轨、POC 边界、主题装订、
规范卫生 ADR、审核工具。它**不是** DiskHNSW 产品行为契约树。

## 读序（按角色）

| 角色 | 先读 |
|------|------|
| 指挥 / 流程 | 仓库根 [`AGENTS.md`](../../AGENTS.md) → 本 README → [`language.md`](language.md) → [`process.md`](process.md) |
| 产品契约 | [`../00-charter/`](../00-charter/)…`50-verification/` + 产品 [`../open/`](../open/) |
| 审核 / harness 治理 | [`tools/GOVERNANCE.md`](tools/GOVERNANCE.md) → [`tools/HARNESS.md`](tools/HARNESS.md) → [`tools/`](tools/) → [`../INDEX.md`](../INDEX.md) |
| 可移植包（跨 Agent Init） | [`../../packages/ndf-harness/`](../../packages/ndf-harness/)（≥0.2.0；**可能滞后**；以本地本目录为准；禁止用包反推本地） |
| **Workflow 特性总览** | [`../../packages/ndf-harness/docs/WORKFLOW-FEATURES.md`](../../packages/ndf-harness/docs/WORKFLOW-FEATURES.md)（从 Meta 提炼的能力索引；非条款 SoT） |
| 探索 | [`../../poc/README.md`](../../poc/README.md) + `poc/<topic>/ndf/` |

## 本目录内容

| 读什么 | 路径 |
|--------|------|
| **NDF 语言 SoT** | [`language.md`](language.md)（[[META-001]]…[[META-005]]、[[META-008]] 工作空间视角；性能 SLA↔旋钮图依赖 / `trunk-ref` 见 [[META-005]]） |
| 流程纪律 | [`process.md`](process.md)（[[CHR-008]]、[[BEH-018]]…[[BEH-020]]、[[BEH-025]]、[[META-006]]、[[META-007]]、[[META-009]]…[[META-015]]） |
| 目录边界 | [`architecture.md`](architecture.md)（[[ARCH-008]]） |
| POC↔SLA | [`constraints.md`](constraints.md)（[[CON-POC-001]]） |
| 术语 | [`glossary.md`](glossary.md)（[[DEF-020]]…[[DEF-023]]、[[DEF-META-ID-NS]]、DEF-NDF-*） |
| **Harness 治理架构（参考）** | [`tools/GOVERNANCE.md`](tools/GOVERNANCE.md) |
| **Portable Harness（分发 / Init）** | [`tools/HARNESS.md`](tools/HARNESS.md) · [`../../packages/ndf-harness/`](../../packages/ndf-harness/)（**可能滞后**；以本地本目录为准；统一重提炼另案；禁止用包反推本地） |
| 卫生 ADR | [`decisions/`](decisions/)（[[ADR-META-001]]、[[ADR-META-002]]…） |
| 流程提案 | [`open/proposal-meta-*.md`](open/)（及迁入的装订器提案） |
| 审核 harness 命令 | [`tools/README.md`](tools/README.md) |
| Workflow commander / Genesis | [`.cursor/skills/ndf-workflow-canvas/`](../../.cursor/skills/ndf-workflow-canvas/) + [`cockpit/`](cockpit/) + [`tools/ndf_workflow_status.py`](tools/ndf_workflow_status.py) |
| 卫生收口 r2 | [`open/proposal-meta-trunk-hygiene-r2.md`](open/proposal-meta-trunk-hygiene-r2.md) |

## 条款 ID 命名空间（[[ADR-META-002]]）

| 规则 | 说明 |
|------|------|
| **新建一般条款** | `META-nnn`（自 `META-001`）；勿开 `META-BEH-*` / `META-CHR-*` |
| **语义前缀** | `DEF-NDF-*`、`CON-POC-*`、`ADR-META-*` / `ADR-TOPIC-*`、`DEC-HYGIENE-*` |
| **冻结不换号** | `CHR-008`、`BEH-018`…`026`、`ARCH-008`、`DEF-020`…`023` |
| **禁止** | 新 process 条款续产品 `CHR`/`BEH`/`ARCH`/`DEF`/`CON-SLA` 数字号 |

产品契约仍在 `spec/00–50` + `spec/decisions/`（产品 DEC）+ `spec/open/`（**仅产品域**提案）。
产品树中对应段落为 **adopted 薄指针（非 SoT 正文）**，不得把元条款长文写回 `20-behavior/`。

新项目先按 [[META-009]] 走 `track=bootstrap`（greenfield/adopt）建立 Project Genesis；
日常 Proposal/POC 再按 [[META-010]] 门禁回执与 [[META-011]] 派生工作台编排。
Agent 任务上下文按 [[META-012]] 由本地 Context Compiler 统一生成：binder→NDF 图→
git/evidence→gate/runtime→角色权限；不同角色 plan 共享 Task Manifest。可写委派按
[[META-013]] 进入内容寻址 Episode；R0/R1/R2/R3 分级回放，不承诺逐 token 确定性。
回放「已执行」按 [[META-015]] 要求 Lvm guest-proof；提示词与同机 worktree 不得冒充。
新托管 process proposal 按 [[META-014]] 绑定生命周期、人口令回执、stage-specific
child Episode 与幂等 dispatch；历史无绑定提案只读显示为 `legacy_*_unbound`。
既有健康棕地可显示 `operational_legacy`，不因缺历史 Genesis 而停止运作。
Canvas 默认监控本地 Business Project（产品 `spec/00–50` + Trunk）；本目录只作为
Governance/Control 子视图，MUST NOT 冒充业务项目。Topics 的 NDF Control 文档流
委派 OpenClaw；实现代码走 Claude Code。**所有 pack MUST 含 `workspace.repo_root`**；
项目 state 在 `{repo_root}/.openclaw/state.json`，与 gateway session 分离。

分层决策见 [`decisions/adr-meta-layer-split.md`](decisions/adr-meta-layer-split.md)
（[[ADR-META-001]]）。编号命名空间见 [`decisions/adr-meta-id-namespace.md`](decisions/adr-meta-id-namespace.md)
（[[ADR-META-002]] / [[DEF-META-ID-NS]]）。
