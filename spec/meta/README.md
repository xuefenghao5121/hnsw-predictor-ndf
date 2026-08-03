# NDF Process Profile（本仓元规范）

> **role:** ndf-process-profile  
> **product_behavior:** false  
> **sot:** true（对本仓 Agent **流程纪律**）；**false**（对 DiskHNSW **检索/缓存/SLA 产品行为**）

本目录是仓库对 NDF 的 **process profile**：探索/晋升双轨、POC 边界、主题装订、
规范卫生 ADR、审核工具。它**不是** DiskHNSW 产品行为契约树。

## 读序（按角色）

| 角色 | 先读 |
|------|------|
| 指挥 / 流程 | 仓库根 [`AGENTS.md`](../../AGENTS.md) → 本 README → [`process.md`](process.md) |
| 产品契约 | [`../00-charter/`](../00-charter/)…`50-verification/` + 产品 [`../open/`](../open/) |
| 审核工具 | [`tools/`](tools/) → 生成 [`../INDEX.md`](../INDEX.md) |
| 探索 | [`../../poc/README.md`](../../poc/README.md) + `poc/<topic>/ndf/` |

## 本目录内容

| 读什么 | 路径 |
|--------|------|
| 流程纪律 | [`process.md`](process.md)（[[CHR-008]]、[[BEH-018]]…[[BEH-020]]、[[BEH-025]]） |
| 目录边界 | [`architecture.md`](architecture.md)（[[ARCH-008]]） |
| POC↔SLA | [`constraints.md`](constraints.md)（[[CON-POC-001]]） |
| 术语 | [`glossary.md`](glossary.md)（[[DEF-020]]…[[DEF-023]]） |
| 卫生 ADR | [`decisions/`](decisions/) |
| 流程提案 | [`open/proposal-meta-*.md`](open/)（及迁入的装订器提案） |
| 审核 harness | [`tools/`](tools/)（`ndf_index.py`；原 `tools/ndf/`） |

产品契约仍在 `spec/00–50` + `spec/decisions/`（产品 DEC）+ `spec/open/`（**仅产品域**提案）。
产品树中对应段落为 **adopted 薄指针（非 SoT 正文）**，不得把元条款长文写回 `20-behavior/`。

分层决策见 [`decisions/adr-meta-layer-split.md`](decisions/adr-meta-layer-split.md)。
