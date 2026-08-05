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
| 可移植包（跨 Agent Init） | [`../../packages/ndf-harness/`](../../packages/ndf-harness/) |
| 探索 | [`../../poc/README.md`](../../poc/README.md) + `poc/<topic>/ndf/` |

## 本目录内容

| 读什么 | 路径 |
|--------|------|
| **NDF 语言 SoT** | [`language.md`](language.md)（[[META-001]]…[[META-004]]） |
| 流程纪律 | [`process.md`](process.md)（[[CHR-008]]、[[BEH-018]]…[[BEH-020]]、[[BEH-025]]） |
| 目录边界 | [`architecture.md`](architecture.md)（[[ARCH-008]]） |
| POC↔SLA | [`constraints.md`](constraints.md)（[[CON-POC-001]]） |
| 术语 | [`glossary.md`](glossary.md)（[[DEF-020]]…[[DEF-023]]、[[DEF-META-ID-NS]]、DEF-NDF-*） |
| **Harness 治理架构（参考）** | [`tools/GOVERNANCE.md`](tools/GOVERNANCE.md) |
| **Portable Harness（分发 / Init）** | [`tools/HARNESS.md`](tools/HARNESS.md) · [`../../packages/ndf-harness/`](../../packages/ndf-harness/) |
| 卫生 ADR | [`decisions/`](decisions/)（[[ADR-META-001]]、[[ADR-META-002]]…） |
| 流程提案 | [`open/proposal-meta-*.md`](open/)（及迁入的装订器提案） |
| 审核 harness 命令 | [`tools/README.md`](tools/README.md) |
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

分层决策见 [`decisions/adr-meta-layer-split.md`](decisions/adr-meta-layer-split.md)
（[[ADR-META-001]]）。编号命名空间见 [`decisions/adr-meta-id-namespace.md`](decisions/adr-meta-id-namespace.md)
（[[ADR-META-002]] / [[DEF-META-ID-NS]]）。
