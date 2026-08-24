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

## Init 顺序（1.0）

```bash
python3 packages/ndf-harness/install.py install \
  --repo <consumer> --profile dual-track \
  --runtime cursor,openclaw,claude-code
python3 packages/ndf-harness/install.py verify --repo <consumer> ...
```

安装器一次交付：norms → `spec/`、tools 源码 → `spec/meta/tools/`、`AGENTS.md`、
`ndf.workflow.yaml`、templates、唯一人类入口 skill `ndf-workflow`（五句口令）。  
消费方 **不** 需要回维护仓取 `.py`（见包内 `governance/tools/VENDOR.md`）。

顺序：**规范 → AGENTS.md → 治理工具 → adapter skill → verify**。

## 与 GOVERNANCE 分工

| 文档 | 回答 |
|------|------|
| **HARNESS.md（本文）** | 分发、Init、多运行时、包布局 |
| **GOVERNANCE.md** | index→lint→advise→simulate→human→recheck |

## 非目标

产品域条款、单一 IDE 强绑定、沙盒自动 apply。  
1.0 起 tools **随包完整源码**交付；VENDOR 只说明 pin/复制，不再要求回维护仓取脚本。

## 版本与蒸馏

包版本 **1.0.1**（自包含：角色绑定 + in-host 备选；`tests/`、`MANIFEST.json`）见
[`packages/ndf-harness/VERSION`](../../../packages/ndf-harness/VERSION)。  
蒸馏源 commit：见包内 `MANIFEST.json`。  
**流向**：本地已验证 `spec/meta/` + tools → 蒸馏进本包 → [NDF-Harness](https://github.com/xuefenghao5121/NDF-Harness)。  
**本地 SoT 仍优先**。变更摘要见包内 `CHANGELOG.md`。
