# Proposal: POC 回合 plan harness（ndf_close） {#PROP-META-NDF-CLOSE-PLAN}

> track: process  
> Status: Pending  
> 日期: 2026-08-04  
> 关联: [[BEH-019]], [[BEH-020]], [[BEH-025]], [[DEF-022]], [[CON-POC-001]], [[ADR-META-001]]  
> 场景: 规范卫生 / 双轨收口 harness

## 1. 动机

POC 装订器（`poc/<topic>/ndf/`）与 Trunk SoT（`spec/00–50`）分离后，主题关闭时缺少统一的
**回合计划**面：哪些条款/边追加进原始 NDF 图、散文如何溯源、收口后如何强制验图。

## 2. 决策摘要

1. 新增 harness：`spec/meta/tools/ndf_close.py`（与 `ndf_index` / `ndf_graphcheck` 并列）。
2. 第一版仅 `plan`（只读）：生成 inventory、往 Trunk 图追加的 disposition、POC `source:` 溯源模板、
   装订器归档 checklist、以及 **MUST** 的 post-merge 检查命令。
3. **禁止**把 `poc/*/ndf` 提升为第二套 SoT；evidence 数字不得直接升为 stable must SLA。
4. 不在本提案修改 [[BEH-019]]/[[BEH-020]] 条款 ID；工具落实已有纪律。

## 3. 变更清单

| 位置 | 动作 |
|------|------|
| `spec/meta/tools/ndf_close.py` | 新增 |
| `spec/meta/tools/README.md` | 三工具分工说明 |
| 本文件 | process 提案（Pending → Implemented 待确认） |

## 4. 非目标

- 本版无 `apply`、不自动改 Trunk/`src/`
- 不自动消除全仓既有 meta 环

## 5. 验收

- `plan --topic l4-cache-mgmt --mode partial` 产出含 provenance + post-check 的完整报告
- `plan --mode reject` 产出 deprecate + DEC + archive 清单
