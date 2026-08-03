# DiskHNSW NDF Spec Index

对照 [NDF / normative_language](https://github.com/hengliao1972/normative_language)：树按**子系统归属**，语义靠条款 ID 图，历史靠 git。

## 读序（按角色）

| 角色 | 先读 |
|------|------|
| 指挥 / 流程 | [`../AGENTS.md`](../AGENTS.md) → [`meta/README.md`](meta/README.md) → [`meta/process.md`](meta/process.md) |
| 产品契约 | `00–50` + 产品 [`open/`](open/) |
| 审核工具 | [`meta/tools/`](meta/tools/) → 生成本目录 [`INDEX.md`](INDEX.md) |
| 探索 | [`../poc/README.md`](../poc/README.md) + `poc/<topic>/ndf/` |

| 目录 | 角色 | 本仓库文件 |
|------|------|------------|
| **`meta/`** | **NDF process profile**（流程 SoT；非产品行为） | `process`, `architecture`, `constraints`, `glossary`, `decisions/`, `open/`, **`tools/`** |
| `00-charter/` | 范围与术语（含双轨 **adopted** 指针） | `charter.md`, `glossary.md` |
| `10-architecture/` | 分解（含 POC 边界 **adopted**） | `modules.md` |
| `20-behavior/` | 产品行为契约；`process.md` 仅为 meta **adopted** | `search`, `fine-rerank`, `cache`, … |
| `30-interfaces/` | 对外契约（软件版 pins） | `cli`, `formats`, `cxx-api`, `env` |
| `40-constraints/` | 性能/资源；[[CON-POC-001]] 正文在 meta | `constants`, `sla` |
| `50-verification/` | 验收（类 PICS） | `acceptance.md`, `acceptance-p2.md` |
| `models/` | **L3 参考模型**（金标） | 见 `models/README.md`；禁止 POC 补丁 |
| `decisions/` | **产品** ADR | `01-foundation` …；卫生 ADR 已迁 `meta/decisions/` |
| `open/` | **产品**开放项 | 仅 Pending / Q / 未关闭 CONFLICT |
| `archive/` | **非 SoT 冷存储** | 见 `ndf.yaml` `archive:` |
| `../poc/` | **非 SoT 探索轨** | 见仓库根 `poc/README.md` |

**警告**：`meta/` 条款（`scope=ndf-process`）约束 Agent **怎么管规范**，不是 DiskHNSW 检索算法 must。分层见 [[ADR-META-001]]。

检索：`rg '\{#DEC-059\}' spec/` 或 `rg '\{#BEH-014\}' spec/20-behavior/`。

**审核跳转（推荐）**：

```bash
python3 spec/meta/tools/ndf_index.py index                 # 生成 INDEX.md + graph.json（含 META 组）
python3 spec/meta/tools/ndf_index.py impact BEH-018        # 依赖/反向链接闭包
python3 spec/meta/tools/ndf_index.py diff HEAD~1           # 本次 diff 触及的 ID + impact
python3 spec/meta/tools/ndf_index.py validate              # 断链 [[ID]]
python3 spec/meta/tools/ndf_index.py poc-topics            # 主题装订器一览
```

工具在 `spec/meta/tools/`（process-profile harness），**不**放在产品 `scripts/`；仓库根不再保留 `tools/`。
打开 [`INDEX.md`](INDEX.md) 按 META / Product 点击条款；SoT 仍是各目录 Markdown，INDEX/graph 为生成物。

## 探索 vs 主线（摘要）

```text
open/proposal ──► poc/<topic>/ 多轮实验 ──► 证据
                      │                    │
                      │ 负结果             │ 正结果
                      ▼                    ▼
                 DEC 关闭 + 弃条款      确认 → stable + 干净合入 src/
```

流程细则正文在 [`meta/process.md`](meta/process.md)（[[BEH-018]]…[[BEH-020]]、[[CON-POC-001]]）。
process 提案 → [`meta/open/`](meta/open/)；产品提案 → [`open/`](open/)。
