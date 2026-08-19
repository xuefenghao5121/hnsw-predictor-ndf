# Process 提案：Kernel Map 缺失种子恢复（META-012 / META-013）

> track: process
> Status: Implemented on 2026-08-17
> reviewed: 已审核
> 日期: 2026-08-17
> depends-on: META-011
> 范围: kernel_map missing_seeds / spec health / ndf_index 再索引

## 1. 问题

Canvas Control 的 `kernel_map`（`spec/meta/tools/ndf_workflow_status.py`）报告：

```text
missing_seeds: ["META-012", "META-013"]
```

根因：`kernel_map()` 以 `spec/meta/graph.json` 为输入，`KERNEL_SEED_IDS` **已包含**
`META-012`、`META-013`；但 `spec/meta/graph.json`（及 `INDEX.md`）生成于
`2026-08-12T11:44:45Z`，`clause_count=46`，早于 `META-012`（`since=0.9.14`，
`spec/meta/process.md:545`）与 `META-013`（`spec/meta/process.md:615`）写入稳定正文。
稳定正文（SoT）已含这两条 `status=stable` 条款，而派生的图/索引投影滞后，导致种子在
映射中"缺失"。

这不是稳定正文缺陷，而是**派生投影过期**：`graph.json` / `INDEX.md` 是
`ndf_index.py index` 生成的派生产物（`Do not hand-edit`），未随正文新增条款同步刷新。

## 2. 决策

1. `spec/meta/graph.json` 与 `spec/meta/INDEX.md` 是 `ndf_index.py index` 的派生投影，
   **不是 SoT**；稳定正文新增/改名/删除条款后，MUST 重新运行
   `python3 spec/meta/tools/ndf_index.py index`（本提案的落地动作）。
2. `KERNEL_SEED_IDS` 已含 `META-012`、`META-013`，**无需改种子列表**；修复为纯再索引。
3. `kernel_map` 出现非空 `missing_seeds` 时，spec health SHOULD 记
   `kernel_map_seed_stale` 类 finding（warning），不得静默累积；工具侧 guard 属另案，
   本提案仅作提案级描述，不落地工具实现。

## 3. 变更

- 落地动作：`python3 spec/meta/tools/ndf_index.py index`，重新生成
  `spec/meta/graph.json` + `spec/meta/INDEX.md`，使二者纳入 `META-012`、`META-013`。
- 无稳定正文条款修订；无 `src/` / `include/` / `tests/` 变更；无产品契约改动。

## 4. 验收

1. `spec/meta/graph.json` 含 `META-012`、`META-013`，`clause_count` 由 46 → 48。
2. `kernel_map.missing_seeds == []`（`META-012` / `META-013` 不再缺失）。
3. `spec/meta/INDEX.md` META 段列出 `META-012`、`META-013`。
4. `python3 spec/meta/tools/ndf_graphcheck.py --meta` hard_errors=0。

## 5. 不做（本轮边界）

- 不手改 `graph.json` / `INDEX.md`（必须由 `ndf_index.py index` 生成）。
- 不改 `spec/meta/` 稳定正文（`process.md` / `language.md` / `architecture.md` /
  `constraints.md` / `glossary.md` / `decisions`）。
- 不改 `KERNEL_SEED_IDS` 或工具实现；工具侧 hygiene guard 另案。
- 不引入产品 ID / SLA 数字 / POC 装订器字段。
- 不批门禁、不伪造 `approved_by`、不写 `.openclaw/state.json`。
