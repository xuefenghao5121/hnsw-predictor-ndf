# CLAUDE.md - Claude Code 行为约束

## 绝对禁区
1. 严禁修改 `spec/00-charter/` 和 `spec/10-architecture/`
2. 严禁修改 `spec/20-behavior/` 中 `level=L0` 或 `level=L1` 的条款
3. 严禁修改 `spec/decisions/`
4. 若发现L0/L1条款与代码现实冲突，在 `spec/open/` 下创建 `feedback-*.md` 提案

## 权限范围
- 全权：`src/`, `tests/`, `50-verification/`
- 细化权：`20-behavior/`（L2/L3）、`30-interfaces/`（字段级）、`40-constraints/`（阈值）
- 提案权：若需修改L0/L1/架构，写提案到 `open/`
