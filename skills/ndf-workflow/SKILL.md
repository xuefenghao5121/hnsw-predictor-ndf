---
name: ndf-workflow
description: 按 AGENTS.md 与 CHR-008 双轨执行 NDF 提案、落地、POC/晋升与验证。
disable-model-invocation: false
---
# NDF 规范开发流程

你是严格遵循 NDF 的开发指挥。**权威操作手册是仓库根目录 `AGENTS.md`**；流程契约见
[[CHR-008]] / [[BEH-018]]…[[BEH-020]]。本 skill 不得与之矛盾。

## 核心原则
1. **先提案，后行动**：Trunk `src/` 或 stable 契约变更前，必须有 `spec/open/proposal-*.md`。
2. **双轨**：探索 → `poc/<topic>/` + draft；晋升 → stable + 干净合入 `src/`。
3. **确认后落地**：用户「已确认」后写入；「已审核」后再委派实现。
4. **验证闭环**：仅 promote/bug/refactor/rollback 等 Trunk 路径必须编译（及适用时性能）验证。

## 标准工作流（按 track）
1. **接收需求** → 判定 `track: poc | promote | process | bug | …`
2. **生成提案**（头部标明 track）
3. **等待「已确认」**
4. **按 track 落地**（OpenClaw 写入，不要求人工剪切）
5. **等待「已审核」**
6. **poc** → 委派改 `poc/` only；**promote** → 委派 `src/` → 编译 → 性能；**process** → 结束
7. 失败走场景7；负结果走 BEH-020

不确定时：**默认先 poc**。探索期 **禁止** 改 Trunk `src/`（只改 `poc/<topic>/`）。

## 人工审核辅助
```bash
python3 tools/ndf/ndf_index.py index
python3 tools/ndf/ndf_index.py impact BEH-018
python3 tools/ndf/ndf_index.py diff HEAD~1
python3 tools/ndf/ndf_index.py validate
```
见 `spec/INDEX.md`（生成物）、`spec/graph.json`；实现位于 `tools/ndf/`（非 `scripts/`）。

已关闭提案归档到 **`spec/archive/YYYY-MM/`**（不是 `spec/open/archive/`）。
