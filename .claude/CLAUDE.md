# CLAUDE.md - Claude Code 行为约束

## 绝对禁区
1. 严禁修改 `spec/00-charter/` 和 `spec/10-architecture/`
2. 严禁修改 `spec/20-behavior/` 中 `level=L0` 或 `level=L1` 的条款
3. 严禁修改 `spec/decisions/`
4. 若发现 L0/L1 条款与代码现实冲突，在 `spec/open/` 下创建 `feedback-*.md` 提案
5. **严禁**把实验补丁写入 `spec/models/` 冒充 L3 金标

## 按 track 的写入范围（权威见仓库根 `AGENTS.md`）

| track | 可写 | 禁止 |
|-------|------|------|
| **poc** | `poc/<topic>/` only（含 NOTES、独立源码/bench） | Trunk `src/` 生产默认路径；stable must SLA |
| **promote / bug / refactor / rollback** | `src/`、`tests/`、`50-verification/`；L2/L3；字段级接口 | L0/L1、charter、architecture、decisions |
| **process** | 通常不改代码；若仅文档则听从委派说明 | 擅自改 `src/` |

不确定时：**默认按 poc**，只动 `poc/<topic>/`。

## 权限范围（在 track 允许的前提下）
- Trunk 实现：`src/`, `tests/`, `50-verification/`（仅 promote/bug/refactor/rollback）
- 细化权：`20-behavior/`（L2/L3）、`30-interfaces/`（字段级）、`40-constraints/`（阈值，非 L0/L1 叙事）
- 提案权：若需修改 L0/L1/架构，写提案到 `spec/open/`
