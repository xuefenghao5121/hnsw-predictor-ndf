# NDF Harness Manifest

> Status: **Draft framework** — 人工审核后填写版本与负责人。  
> Last updated: 2026-08-03  
> Owner: ⟨TBD: 人工⟩

## 三角色 ↔ 产物

| 产物路径 | 归属角色 | 生成方 | 说明 |
|----------|----------|--------|------|
| `spec/00–50` | 产品 SoT | Cursor 协助 / OpenClaw L0–L1 | 产品行为 / SLA / 接口 |
| `spec/meta/` | **process profile** | OpenClaw / Cursor | 双轨、POC 边界、装订、卫生 ADR |
| `spec/INDEX.md`, `spec/graph.json` | Cursor 审核面 | `spec/meta/tools/ndf_index.py` | **生成物**（含 META 分组），非 must |
| `spec/meta/tools/**` | Cursor harness | Cursor + 本 skill | 与 `scripts/` 解耦 |
| `scripts/**` | 产品 pipeline | Claude Code / 人工 | **禁止**塞 NDF 审核工具 |
| `AGENTS.md` | OpenClaw | Cursor 脚手架 → 人工定稿 | 大脑操作手册 |
| `skills/ndf-workflow/` | OpenClaw | Cursor 脚手架 → 人工定稿 | 本地 NDF Workflow 技能 |
| `.claude/CLAUDE.md` | Claude Code | Cursor 脚手架 → 人工定稿 | 编码禁区与可写范围（含禁 meta） |
| `.openclaw/state.json` | OpenClaw | **仅 OpenClaw** | 项目进展；Cursor/ndf-harness **禁止写入** |
| `poc/**` | 探索轨 | OpenClaw 指挥 / Claude 实现 | 非 SoT |

## 生成任务类型

| 类型 | 输入 | 输出 stub 落点 |
|------|------|----------------|
| `docs` | 新子系统 / 新前缀 | `spec/` 目录约定说明（不自动造条款） |
| `tools` | 审核能力需求 | `spec/meta/tools/` |
| `prompts-openclaw` | 流程变更 | `AGENTS.md`, `skills/ndf-workflow/`；**同步** `meta/README` |
| `prompts-claude` | 写入边界变更 | `.claude/CLAUDE.md`, ACP 模板 |
| `all` | 新仓 bootstrap | 上表全套 stub |

## 版本记录

| 日期 | 变更 | 审核人 |
|------|------|--------|
| 2026-08-03 | harness 迁至 `spec/meta/tools/` | ⟨TBD⟩ |
| 2026-08-03 | meta 分层：MANIFEST 区分 product vs meta | ⟨TBD⟩ |
| ⟨TBD⟩ | 框架初建（仅目录与模板） | ⟨TBD⟩ |
