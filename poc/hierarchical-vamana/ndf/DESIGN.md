# DESIGN.md — hierarchical-vamana

> topic_id: hierarchical-vamana
> status: draft
> links: TOPIC.md hypothesis / draft BEH-HV-001, ARCH-HV-001

非 SoT；写 HOW。条款 WHAT 见提案与 TOPIC。

<!-- ndf:gate-slice begin=design_contract -->
## Goals / non-goals

- Goals: 分层（HNSW 式）+ 层内 Vamana 建图；导出适配现 DiskHNSW 布局；相对 Trunk 对照测量
- Non-goals: 十亿点 DiskANN 分片合并；改 VER；写 Trunk / stable SLA

## Modules and layout

```text
poc/hierarchical-vamana/
  build/                 # 分层 Vamana 建图（拷贝自 Trunk pipeline 后改）
  export/                # 邻接 → extract / BFS reorder / blocks / PQ 适配
  search/                # 可选：上层下降 + 复用 L0 搜索壳（若需）
  ndf/                   # 本装订器
  evidence/              # 测量证据（mutable）
```

## Data / control flow

```text
vectors
  → assign max layer (HNSW geometric)
  → per-layer: beam/GreedySearch → RobustPrune(α) → directed edges
  → optional 2nd pass α>1 on L0
  → export adjacency
  → (reuse) reorder / write_blocks / PQ
  → search: upper in-mem descent → L0 + Fine Rerank / BlockCache
```

## Trunk boundary

- Copy-then-edit: `src/pipeline/build_index.cpp` 及相关图构建辅助；必要时拷贝搜索侧仅读对接头
- Read-only link: Trunk 搜索路径、PQ、BlockCache、`scripts/run_sustained.sh`、`cfg-sla-ef100`
- MUST NOT write Trunk `src/` / `include/` / `tests/`（[[BEH-018]]）

## Implementation slice

本轮：

1. 在 poc 内落地 Vamana RobustPrune + 层分配骨架
2. 接到现有导出/分块路径（或 poc 内等价最小导出）
3. 跑通构建 + 对照测量入口（见 INTERFACE / PERF_BASELINE）

不改：Trunk 默认 `build_index` 路径、stable SLA、VER 协议正文。

## Failure modes

- 召回 < 对照：调 α / M / beam / 层概率；记录于 DELTA Rounds
- 导出布局不兼容：明确迁移表或 L0-only 回退路径（仍留在 poc）
- 建图过慢：缩小集先证伪，再 SIFT1M

## Verification hooks

- `ndf/PERF_BASELINE.md` Measure；`evidence/` 原始 log
- MUST NOT 从 CON-SLA / SLA 观测表抄数字作 SoT
<!-- ndf:gate-slice end=design_contract -->
