# DELTA.md — feature / hotspot logic space

> topic_id: cluster-gbdt
> status: draft
> created: 2026-08-13
> updated: 2026-08-13 (R0 remeasured)
> links: TOPIC.md / DESIGN.md / PERF_BASELINE.md

**非 SoT**。跟踪相对 Trunk 的功能变化与性能热点迁移。

## Bind snapshot

| leg | id / path |
|-----|-----------|
| vs | bl-trunk-golden-7ee4ee2 |
| config_id | Config C (M=24, EF=60), SIFT1M |
| measure_script | poc/cluster-gbdt/train_cluster_gbdt.py |

## Feature delta

相对 Trunk 的功能/行为变更：

| id | change | links | status |
|----|--------|-------|--------|
| F1 | +1 cluster_purity feature (12th GBDT input) | BEH-034 / DESIGN §Data flow | **dropped** (R0 negative) |
| F2 | cluster_id lookup table (node_id → cluster_id) | DESIGN §Modules | **dropped** (R0 negative) |

## Hotspot delta

| id | hypothesis | measured | links | status |
|----|------------|----------|-------|--------|
| H1 | cluster purity 减少 fine rerank 候选数 | R0: QPS Δ=−0.7% with LEARNED_EF | NOTES.md | **rejected** |
| H2 | GBDT 推理开销 > 剪枝收益 | R0: LEARNED_EF 无增量信号 | NOTES.md | **confirmed** |

<!-- ndf:gate-slice begin=delta_hypothesis -->
## Bind snapshot (current)

| leg | id / path |
|-----|-----------|
| vs | bl-trunk-golden-7ee4ee2 |
| config_id | Config C (M=24, EF=60), SIFT1M |
| measure_script | poc/cluster-gbdt/train_cluster_gbdt.py (R0); scripts/run_sustained.sh (baseline) |

## Current amendment candidates

以下候选不改写 R0 结论；它们只记录在新 Trunk 前提下值得重新验证的假设：

| id | candidate | prerequisite | status |
|----|-----------|--------------|--------|
| A1 | cluster entropy 取代单一 purity | 现行 Trunk R0 重测 | proposed |
| A2 | k=4096/8192 更细粒度 signal | A1 有增量趋势 | deferred |
| A3 | per-cluster predictor | A1/A2 显示跨 cluster 异质性 | deferred |
<!-- ndf:gate-slice end=delta_hypothesis -->

## Rounds

| round | date | bind unchanged? | feature notes | hotspot notes | conclusion |
|-------|------|-----------------|---------------|---------------|------------|
| R0 | 2026-08-10 | yes | 12-feature GBDT trained; cluster purity feature importance ≈ 0 | LEARNED_EF vs default: Δ +1.0% / −0.7% (noise level) | **方向 F = 无显著收益 ❌** |
| R0-remeasure-claim | 2026-08-13 | no — Trunk a143392 vs 1f684c7 | Values written by Control/OpenClaw without a verified measurement lease/completion | claimed agg QPS 1812→2160 (+19%); no evidence artifact found | **unverified; superseded by R0-remeasure-verified** |
| R0-remeasure-verified | 2026-08-14 | no — Trunk a143392 vs 1f684c7 | CON-SLA-020 / cfg-m24-ef60 / cluster k=1024; lease run-repair-poc-measurement-cluster-gbdt-20260814T083515Z | 512MB agg=2249 steady=2539 recall=96.59% RSS=332; 256MB agg=1805 steady=2042 recall=96.60% RSS=231; vs historical R0 +24.1% agg | **verified R0; baseline_status=current** |
| R1-entropy | 2026-08-14 | yes — Trunk a143392 | groundtruth top-100 entropy/purity/dominant_frac; k=1024 assignments | entropy=0.9945 (saturated) purity=0.063 dominant_frac=0.024; top-100 spans ~94/1024 clusters; no concentration | **A1 rejected: no incremental signal ❌** |
