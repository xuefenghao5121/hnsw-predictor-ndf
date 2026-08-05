# NDF Portable Harness（分发参考）

> **role:** ndf-process-reference  
> **product_behavior:** false  
> **scope:** ndf-process  
> **package:** [`packages/ndf-harness/`](../../../packages/ndf-harness/)  
> **proposal:** [`../open/proposal-meta-ndf-portable-harness.md`](../open/proposal-meta-ndf-portable-harness.md)  
> **runtime governance:** [`GOVERNANCE.md`](GOVERNANCE.md)

本文说明 **如何把 NDF 装进任意工程并跨 Agent 使用**。日常修图纪律见 GOVERNANCE。

## 三等产物

1. **Norms** — `packages/ndf-harness/norms/` → `spec/meta` + 空产品树  
2. **Workflow** — `workflow/AGENTS.md` → 仓库根（跨 OpenClaw / Claude Code / OpenCode / Cursor …）  
3. **Governance** — tools via VENDOR + GOVERNANCE 主链  

Skill 核心在 `packages/ndf-harness/skill/`；各运行时只用 `adapters/<runtime>/` 薄挂载。

## Init 顺序

规范 → `AGENTS.md` → 取得工具 →（可选）adapter → 基线 linter。

## 与 GOVERNANCE 分工

| 文档 | 回答 |
|------|------|
| **HARNESS.md（本文）** | 分发、Init、多运行时、包布局 |
| **GOVERNANCE.md** | index→lint→advise→simulate→human→recheck |

## 非目标

产品域条款、单一 IDE 强绑定、沙盒自动 apply、工具双头复制（见 VENDOR.md）。
