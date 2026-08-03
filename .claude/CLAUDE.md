# CLAUDE.md - Claude Code 行为约束

## 绝对禁区
1. 严禁修改 `spec/00-charter/` 和 `spec/10-architecture/`
2. 严禁修改 `spec/meta/`（NDF process profile；仅 OpenClaw / Cursor 维护）
3. 严禁修改 `spec/20-behavior/` 中 `level=L0` 或 `level=L1` 的条款
4. 严禁修改 `spec/decisions/` 与 `spec/meta/decisions/`
5. 若发现 L0/L1 与代码现实冲突：
   - **产品契约** → `spec/open/feedback-*.md`
   - **流程/双轨/装订** → `spec/meta/open/feedback-*.md`（或交 OpenClaw 开 process 提案）
6. **严禁**把实验补丁写入 `spec/models/` 冒充 L3 金标

## 按 track 的写入范围（权威见仓库根 `AGENTS.md`）

| track | 可写 | 禁止 |
|-------|------|------|
| **poc** | `poc/<topic>/` only（含 NOTES、独立源码/bench、ndf 装订器证据） | Trunk `src/` 生产默认路径；stable must SLA；`spec/meta/` |
| **promote / bug / refactor / rollback** | `src/`、`tests/`、`50-verification/`；L2/L3；字段级接口 | L0/L1、charter、architecture、decisions、**meta** |
| **process** | **不得**自行改 meta/产品条款；若委派仅改 `poc/` 文档则听从说明 | 擅自改 `src/` 或 `spec/meta/` |

不确定时：**默认按 poc**，只动 `poc/<topic>/`。

## 权限范围（在 track 允许的前提下）
- Trunk 实现：`src/`, `tests/`, `50-verification/`（仅 promote/bug/refactor/rollback）
- 细化权：`20-behavior/`（L2/L3）、`30-interfaces/`（字段级）、`40-constraints/`（阈值，非 L0/L1 叙事）
- 提案权：产品 L0/L1 冲突 → `spec/open/`；流程冲突 → 交给 OpenClaw（`spec/meta/open/`）
