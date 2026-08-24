# Proposal: 绑定溯源顾问（ndf_advise --surface bind） {#PROP-META-NDF-BIND-ADVISE}

> track: process  
> Status: Implemented on 2026-08-04  
> 日期: 2026-08-04  
> 关联: [[DEF-NDF-REPRO-BIND-GAP]], [[DEF-NDF-BINDER-DUAL-HEAD]], [[DEF-NDF-OBS-GRAIN]], [[DEF-NDF-ZOMBIE-SPEC]], [[DEF-NDF-SPEC-DRIFT]], [[BEH-025]], [[DEF-022]], [[DEF-023]], [[BEH-026]]  
> 场景: 规范卫生 / 绑定溯源人机协同  
> scope: ndf-process  
> depends-on: proposal-meta-ndf-graph-advise, proposal-meta-ndf-bindcheck

## 1. 动机

v1 `ndf_advise` 只覆盖图语义面。绑定溯源面（原 Layer B）已有 Linter `ndf_bindcheck`，
需要同一套顾问壳：Issue Queue + RefactorOptions + Impact_Delta + 沙盒，**禁止**静默改 git / SoT。

## 2. 决策摘要

1. 扩展 `ndf_advise.py`：`--surface bind`（默认仍为 `graph`）。
2. 实现模块：`spec/meta/tools/ndf_advise_bind.py`（复用 bindcheck findings）。
3. Issue Queue 优先级：`draft_vs_stable` / DUAL-HEAD → `missing_trailer` / BIND-GAP → `clause_unbound` → grain → zombie/drift。
4. Action Registry（绑定面）：
   - `update_topic_draft_table` — TOPIC draft 登记与 Trunk stable 对齐
   - `append_ledger_row` — 虚拟 COMMITS 行
   - `add_not_backfilled_banner` — 历史豁免头
   - `add_trailers_template` — 应补 trailer 模板（**不**改 git）
   - `lengthen_ledger_note` — OBS-GRAIN
   - `fix_path_cite` — 僵尸路径（虚拟文本替换）
5. 沙盒：内存中的 TOPIC.md + COMMITS.md 文本；**永不** `git commit --amend` / 写盘。
6. `missing_trailer` 的 sandbox pass 含义：装订器/ledger 意图一致或模板已生成；**仍可能**被 bindcheck 扫到历史无 trailer 提交（需 `--since` 或接受历史债）。
7. MUST NOT 改 `.openclaw/state.json`；MUST NOT 产品树 adopted。

## 3. CLI

```bash
python3 spec/meta/tools/ndf_advise.py plan --surface bind --low-hanging-fruit \
  --report tmp/ndf-advise-bind.md
python3 spec/meta/tools/ndf_advise.py simulate --surface bind \
  --issue dual-001 --option O1 --report tmp/ndf-advise-bind-sim.md
```

## 4. 变更清单

| 位置 | 动作 |
|------|------|
| `spec/meta/tools/ndf_advise_bind.py` | 新增 |
| `spec/meta/tools/ndf_advise.py` | `--surface graph|bind` |
| `spec/meta/tools/README.md` | 文档 |
| `proposal-meta-ndf-graph-advise.md` | v2 指针改为已落地 |
| 本文件 | Implemented |

## 5. 非目标

- 改写 git history、自动写 TOPIC/COMMITS、Canvas UI、provenance_depth_delta

## 6. 验收

- bind plan 含 DUAL-HEAD / BIND-GAP 类 RefactorOptions  
- simulate 对 `update_topic_draft_table` / `append_ledger_row` 可 pass，且零写盘  
