# Proposal: 交互式图顾问 harness（ndf_advise） {#PROP-META-NDF-GRAPH-ADVISE}

> track: process  
> Status: Implemented on 2026-08-04  
> 日期: 2026-08-04  
> 关联: [[DEF-NDF-GRAPH]], [[DEF-NDF-CYCLE]], [[DEF-NDF-STABLE-DRAFT]], [[DEF-NDF-CONFLICT-ASYM]], [[DEF-NDF-META-DANGLING]], [[DEF-NDF-UNLINKED]], [[DEF-NDF-REPRO-BIND-GAP]], [[DEF-NDF-BINDER-DUAL-HEAD]], [[DEF-NDF-OBS-GRAIN]], [[DEF-NDF-ZOMBIE-SPEC]], [[DEF-NDF-SPEC-DRIFT]], [[BEH-026]], [[CHR-008]]  
> 场景: 规范卫生 / 人机协同图重构工作台  
> scope: ndf-process  
> depends-on: proposal-meta-ndf-defect-taxonomy, proposal-meta-ndf-bindcheck

## 1. 动机

`ndf_graphcheck` / `ndf_bindcheck` 已是 Linter，输出问题多时认知过载。
需要顾问层：把图论/绑定问题降维为带 **Impact_Delta** 的局部决策菜单，并支持沙盒推演。
**禁止**静默自动修主图（防语义灾难）。

## 2. 分期

| 阶段 | 面 | Linter | 顾问 |
|------|----|--------|------|
| **v1** | 图语义面 | `ndf_graphcheck` | `ndf_advise plan/simulate --surface graph` |
| **v2（本仓库已落地）** | 绑定溯源面 | `ndf_bindcheck` | `ndf_advise … --surface bind`（见 `proposal-meta-ndf-bind-advise`） |

## 3. 决策摘要（v1）

1. 新增 `spec/meta/tools/ndf_advise.py`；不并入 index；不静默写 `spec/**`。
2. Issue Queue 优先级：`stable_dep` → 最小 `cycle` → `conflict_asym` / `meta_dangling` → `unlinked`。
3. Action Registry（仅允许既有 EDGE_KEYS；**禁止**发明 `mentions`）：
   `remove_edge` | `retarget_edge` | `change_rel` | `insert_iface` | `deprecate_node` | `mirror_conflict`
4. 每选项：`Impact_Delta`、`confidence`、`sandbox_patch`。
5. `simulate`：内存图拷贝 + 原子 patch + 复跑 graphcheck 谓词；未解当前问题或新增 cycle/stable_dep → fail。
6. `--low-hanging-fruit`：只展开 high confidence；仍不写盘。
7. MUST NOT 改 `.openclaw/state.json`；MUST NOT 产品树 adopted。

## 4. v2 绑定溯源面

已另案落地：[`proposal-meta-ndf-bind-advise.md`](proposal-meta-ndf-bind-advise.md)。  
CLI：`ndf_advise.py plan|simulate --surface bind`。

## 5. 变更清单

| 位置 | 动作 |
|------|------|
| `spec/meta/tools/ndf_advise.py` | 新增 plan + simulate |
| `spec/meta/tools/README.md` | 五工具分工 |
| 本文件 | Implemented |

## 6. 非目标（v1/v2 共用）

- Canvas / REPL、自动 apply SoT、LLM 内嵌调用、改写 git history
- provenance_depth_delta（可选后续）

## 7. 验收

```bash
python3 spec/meta/tools/ndf_advise.py plan --low-hanging-fruit --report tmp/ndf-advise.md
python3 spec/meta/tools/ndf_advise.py simulate --issue <id> --option <opt> --report tmp/ndf-advise-sim.md
```
