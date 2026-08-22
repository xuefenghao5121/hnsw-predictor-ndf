# Proposal: 绑定溯源检查 harness（ndf_bindcheck） {#PROP-META-NDF-BINDCHECK}

> track: process  
> Status: Implemented on 2026-08-04  
> 日期: 2026-08-04  
> 关联: [[DEF-NDF-GRAPH]], [[DEF-NDF-SPEC-DRIFT]], [[DEF-NDF-ZOMBIE-SPEC]], [[DEF-NDF-REPRO-BIND-GAP]], [[DEF-NDF-OBS-GRAIN]], [[DEF-NDF-BINDER-DUAL-HEAD]], [[BEH-025]], [[BEH-026]], [[DEF-022]], [[DEF-023]], [[CHR-008]]  
> 场景: 规范卫生 / 绑定溯源可观测  
> scope: ndf-process  
> depends-on: proposal-meta-ndf-defect-taxonomy  
> supersedes: proposal-meta-ndf-layerb-check（工具曾名 `ndf_layerb`，过泛）

## 1. 动机

缺陷 taxonomy 已定义「绑定溯源面」（条款↔commit↔装订器↔路径；曾称 Layer B），
但缺少可运行检查：`ndf_graphcheck` 只覆盖图语义面（Layer A）。
可回溯要求对 ledger/trailer、装订器双头、路径僵尸与时间线漂移做自动化门闩。

工具名 MUST 表意检查内容，故用 **`ndf_bindcheck`**（非泛称 layerb）。

## 2. 决策摘要

1. 独立工具 `spec/meta/tools/ndf_bindcheck.py`（不并入 `ndf_index`）。
2. v1 默认：`bind`（[[DEF-NDF-REPRO-BIND-GAP]]）、`dual`（[[DEF-NDF-BINDER-DUAL-HEAD]]）、`grain`（[[DEF-NDF-OBS-GRAIN]]，warning）。
3. v1 可选：`zombie`、`drift`（warning；启发式；非图论语义需人工）。
4. 硬错误 exit 1：`REPRO-BIND-GAP`、`BINDER-DUAL-HEAD`。
5. 只落 `spec/meta/`；MUST NOT 在产品 `00–50` 增加 adopted。
6. MUST NOT 改 `.openclaw/state.json`。

## 3. 判定与严重级别

| check | DEF | severity v1 | 摘要 |
|-------|-----|-------------|------|
| bind | REPRO-BIND-GAP | error | `poc/<topic>` 代码提交缺 `Topic:`/`Clauses:`；ledger sha 不存在 |
| dual | BINDER-DUAL-HEAD | error | TOPIC 仍标 draft 但 Trunk 已 stable（或反向未收口） |
| grain | OBS-GRAIN | warning | 同 protocol 多 code_commit 且 note 过短；单行 clauses 过多 |
| zombie | ZOMBIE-SPEC | warning | topic 条款/提案中路径 token 在仓库不存在 |
| drift | SPEC-DRIFT | warning | 近期触达路径与条款引用相交但无 ledger/trailer 绑定 |

## 4. 变更清单

| 位置 | 动作 |
|------|------|
| `spec/meta/tools/ndf_bindcheck.py` | 新增（自 `ndf_layerb` 更名落地） |
| `spec/meta/tools/README.md` | 四工具分工 |
| 本文件 | Implemented；旧 `proposal-meta-ndf-layerb-check` 标 Superseded |

## 5. 非目标

- 全 C++ 符号表、行为 must 证明、自动修 ledger、git 1:1  
- 重写 `ndf_graphcheck` DEF 输出对齐（另案）  

## 6. 验收

```bash
python3 spec/meta/tools/ndf_bindcheck.py check --topic l4-cache-mgmt
python3 spec/meta/tools/ndf_bindcheck.py check --all-topics
```
