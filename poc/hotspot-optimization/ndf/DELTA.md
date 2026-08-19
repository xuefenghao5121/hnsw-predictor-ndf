# DELTA.md — feature / hotspot logic space

> topic_id: hotspot-optimization
> status: draft
> created: 2026-08-18
> links: TOPIC.md / DESIGN.md / PERF_BASELINE.md

复制自 `spec/meta/templates/poc/DELTA.md.stub`。`DESIGN已审核` 后、写 INTERFACE 前 MUST 有骨架（[[BEH-025]]）。
**非 SoT**。跟踪相对 Trunk 的功能变化与性能热点迁移；数字仍以 PERF_BASELINE / evidence 为准。

<!-- ndf:gate-slice begin=delta_hypothesis -->
## Bind snapshot

开题钉死的对照金标（改绑 MUST 更新本表并记 Rounds）：

| leg | id / path |
|-----|-----------|
| vs | bl-trunk-golden-7ee4ee2 |
| config_id | cfg-m24-ef60 |
| measure_script | scripts/run_sustained.sh |

## Feature delta

相对 Trunk 的功能/行为变更（条目化；链 DESIGN 模块）：

| id | change | links | status |
|----|--------|-------|--------|
| F1 | SIMD-gather lookup for `DiskHNSW::pqDistance` (M=32 ADC table) | DESIGN D1 / H1 | planned |
| F2 | RaBitQ 1-bit quantizer replacing PQ (rotation vs HNSW graph first) | DESIGN D2 / H2 · [[DEC-072]] | planned (optional later) |
| F3 | VisitedList pool + adaptive WILLNEED at `NUM_THREADS≥8` | DESIGN D3 / H3 | planned (optional later) |
| F4 | Further candidate compression | DESIGN D4 / H4 | dropped (not recommended) |

## Hotspot delta

预期热点迁移（CPU / IO / lock / cache）。链 PERF Numbers 或 `evidence/`；
**MUST NOT** 抄产品 SLA 观测表作 SoT。此处属测试空间的解释性叙述，不能覆盖
PERF Numbers（比较/决策 SoT）或原始 evidence（审计/复现证据）；冲突见 [[META-008]]。

| id | hypothesis | measured | links | status |
|----|------------|----------|-------|--------|
| H1 | SIMD gather/shuffle cuts `pqDistance` CPU (37.9% @4T in prior evidence); e2e QPS gain capped by I/O | pending R0 | PERF_BASELINE.md · multi-thread-scaling evidence | open |
| H2 | RaBitQ 1-bit is faster iff random rotation stays compatible with the HNSW graph | pending | DESIGN D2 · [[DEC-072]] | open |
| H3 | VL pool + adaptive WILLNEED reduces memset / kernel-lock share at ≥8T | pending | DESIGN D3 | open |
<!-- ndf:gate-slice end=delta_hypothesis -->

## Rounds

| round | date | bind unchanged? | feature notes | hotspot notes | conclusion |
|-------|------|-----------------|---------------|---------------|------------|
| R0 | pending | yes | not run | not run | pending |
