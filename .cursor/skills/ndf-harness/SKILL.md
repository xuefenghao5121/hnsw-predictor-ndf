---
name: ndf-harness
description: >-
  Scaffold and unify NDF harness artifacts for this repo: Cursor review aids,
  OpenClaw AGENTS/skills prompts, Claude Code CLAUDE.md constraints, and
  tools/ndf review scripts. Use when creating or regenerating NDF governance
  files, prompt packs, ndf-index tooling, or when the user mentions NDF harness,
  三角色, OpenClaw/Claude Code 提示文件, or 统一生成管理.
disable-model-invocation: true
---

# NDF Harness（Cursor 侧统一生成框架）

## 角色（本仓库约定）

| 角色 | 职责 | 主要读什么 |
|------|------|------------|
| **Cursor**（眼睛） | NDF 文档审核/修改/变更监控；生成与维护 harness | `spec/`、本 skill、`tools/ndf/` |
| **OpenClaw**（大脑） | 读 NDF 后做设计与指挥；不写 Trunk `src/` | `AGENTS.md`、`skills/ndf-workflow/`、`spec/` |
| **Claude Code**（手脚） | 编码、测试、L2/L3、验证执行 | `.claude/CLAUDE.md`、委派指令、`src/`/`tests/` |

本 skill **只给 Cursor** 用：统一**脚手架/清单/模板路径**。本仓库已有成熟 NDF，
**默认不生成/不覆盖** `AGENTS.md`、条款正文或 Claude 提示初版；仅在用户显式要求时
按 templates 做增量脚手架。

权威产品流程仍以 `AGENTS.md` + `spec/20-behavior/process.md`（[[CHR-008]] / [[BEH-018]]…）为准。本 skill 不得与之矛盾。

## 调用方式

`disable-model-invocation: true` — **不会自动启用**。需要时在对话中点名，例如：
「用 ndf-harness …」或「按 NDF harness skill …」。

## 何时启用

- 「生成 / 更新 NDF harness」「统一管理提示文件」
- 新建 OpenClaw skill / 刷新 CLAUDE 禁区说明
- 增补 `tools/ndf/` 审核工具（**禁止**放进产品 `scripts/`）
- 初始化 `spec/` 目录骨架或 INDEX 生成约定

## 统一管理范围（Manifest）

详见 [MANIFEST.md](MANIFEST.md)。三类产物：

1. **NDF 文档面**：`spec/**` 约定、INDEX/graph 生成入口  
2. **工具面**：`tools/ndf/**`（与产品 `scripts/` 解耦）  
3. **提示面**：
   - OpenClaw：`AGENTS.md`、`skills/ndf-workflow/SKILL.md`
   - Claude Code：`.claude/CLAUDE.md`（及可选 ACP 委派模板）

## 工作流（框架）

复制清单并勾选：

```text
Harness task:
- [ ] 1. 确认变更属于哪一类：docs | tools | prompts | all
- [ ] 2. 读 MANIFEST.md + 现有目标文件（勿盲目覆盖）
- [ ] 3. 从 templates/ 复制 stub 到目标路径（或刷新 ⟨TBD⟩ 段）
- [ ] 4. 标注 Status: Draft — 等待人工审核
- [ ] 5. 人工回复「已确认生成」后再填初版正文 / 跑工具
- [ ] 6. 更新 MANIFEST 版本与日期
```

### 生成原则

- **框架优先**：目录、标题、必填字段、交叉引用占位  
- **人工闸门**：未经「已确认生成」，只提交 stub  
- **路径隔离**：审核脚本 → `tools/ndf/`；产品数据脚本 → `scripts/`  
- **单源流程**：track/poc/promote 文字与 `AGENTS.md` 保持一致，重复段落用「见 AGENTS §x」引用，避免双份漂移  
- **OpenClaw skill ≠ Cursor skill**：`skills/ndf-workflow` 约束大脑；`.cursor/skills/ndf-harness` 约束眼睛的生成动作

## 模板入口

| 模板 | 用途 |
|------|------|
| [templates/openclaw-agents.stub.md](templates/openclaw-agents.stub.md) | `AGENTS.md` 结构骨架 |
| [templates/openclaw-ndf-workflow.stub.md](templates/openclaw-ndf-workflow.stub.md) | `skills/ndf-workflow/SKILL.md` |
| [templates/claude-code.stub.md](templates/claude-code.stub.md) | `.claude/CLAUDE.md` |
| [templates/tools-ndf-readme.stub.md](templates/tools-ndf-readme.stub.md) | `tools/ndf/README.md` |
| [templates/acp-delegate.stub.md](templates/acp-delegate.stub.md) | 委派 Claude Code 的指令块 |

填写规范见 [reference.md](reference.md)。

## 禁止

- 把 NDF 审核工具写入 `scripts/`
- 用本 skill 直接改 `src/` / 跑产品 benchmark
- 静默覆盖已有人工定稿的 `AGENTS.md` / `CLAUDE.md`（必须 diff 提示）
- 在 stub 阶段写入 stable must SLA 或虚构 ACP session 行为
- **改写 `.openclaw/state.json`**：该文件只记录 OpenClaw 指挥的**项目进展**（提案/track/验证）；
  Cursor 侧 NDF 维护（INDEX、harness、提示脚手架）**不得**写入，OpenClaw 不感知此类工作
