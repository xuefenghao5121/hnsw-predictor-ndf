# TOPIC: hotspot-optimization

> topic_id: hotspot-optimization
> status: exploring
> created: 2026-08-18
> track: poc
> baseline_status: n/a
> baseline_trunk_sha: a14339234133cc6c5a2348464954f744c6465efb
> baseline_protocol: CON-SLA-020 sustained, CON-SLA-014 strict cgroup, CON-SLA-019 禁预热
> perf_baseline: ndf/PERF_BASELINE.md
> next_gate: n/a
> selected_decision: partial
> next_round_focus: D1 partial promote (DELTA R1 +2.66% QPS, recall unchanged); D2/F2 dropped per DEC-072 feasibility

Runtime/baseline/next_gate headers above are mutable navigation and sit outside the human review slice.

<!-- ndf:gate-slice begin=topic_contract -->
> explore_surface: pq-codes,mt-scaling
> depends_on_topics: multi-thread-scaling, pq-quality
> conflicts_with_topics: []

## 概述

按可行性排序探索 DiskHNSW 当前 CPU 热点（画像来自已有 evidence，非本主题新采集）：
头号热点是 Phase A `pqDistance`（约 37.9% CPU @4T），本质是 M=32 次随机 gather+add。
诚实 sustained 下宏观仍是 I/O bound；本主题挖的是 I/O 之外最大的 CPU 项。

开题扫描：当前无活跃 exploring 主题，表面 `pq-codes,mt-scaling` 不与任何 exploring 相交。
依赖已关闭主题：`multi-thread-scaling`（promoted，瓶颈画像）；`pq-quality`（rejected，
OPQ 旋转与 HNSW 图不兼容，作为 D2 RaBitQ 的前车之鉴）。

## Active Hypothesis

**H1 (推荐优先 / D1)**：把 `pqDistance` 的 M=32 次标量查表改为 SIMD 字节 shuffle /
批量 gather（FastScan / QuickerADC 式），距离数值保持一致，故 Recall@10 不变；
4T 场景端到端 QPS 应可见提升，上限受 I/O 占比约束。

备选（人工按可行性挑选，不默认并行）：
- **H2 / D2**：RaBitQ 1-bit 量化替代 PQ。MUST 先验证随机旋转与 HNSW 图兼容（[[DEC-072]]）。
- **H3 / D3**：VisitedList 池化 + `NUM_THREADS≥8` 时自适应禁用 WILLNEED。低复杂度、收益低-中。
- **H4 / D4**：候选数再压缩。不推荐：[[DEC-072]] 已证 recall≥95% 下近天花板。

## Proposals

| Path | Status | Role |
|------|--------|------|
| `spec/open/proposal-poc-hotspot-optimization.md` | Implemented on 2026-08-18 | root |
| `poc/hotspot-optimization/ndf/proposals/proposal-poc-hotspot-optimization.md` | stub → spec/open/ | pointer |

## Draft Clauses

无（本提案不新增 Trunk must / DEC / SLA；不写 `spec/20-behavior/`）

## 非目标

- 不改 [[CHR-006]] Recall@10 ≥ 95%。
- 不写 `src/` / `include/` / `tests/`（[[BEH-018]] §6）；实现仅在收到「可以开始实现」后委派 `poc/hotspot-optimization/`。
- 网上论文数字不是本仓观测，不得写成 must SLA。
<!-- ndf:gate-slice end=topic_contract -->
