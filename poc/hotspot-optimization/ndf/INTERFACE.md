# INTERFACE.md — POC call surface

> topic_id: hotspot-optimization
> status: draft
> created: 2026-08-18
> links: DESIGN.md / PERF_BASELINE.md / DELTA.md

复制自 `spec/meta/templates/poc/INTERFACE.md.stub`。开题实现前 MUST 存在（[[BEH-025]]）。
**非** `spec/30-interfaces/` stable SoT；拟升 Trunk 的切片走 draft→stable 提案。
这是 Design Space 的 POC 调用面，不替代产品 L1 API。

<!-- ndf:gate-slice begin=interface_contract -->
## Entry points

- CLI / scripts: `scripts/run_sustained.sh --config cfg-m24-ef60` (Measure; no new topic script this hop)
- Library symbols: `DiskHNSW::pqDistance`, `DiskHNSW::buildPqDistTable` (unchanged signature; D1 edits the lookup body only)

## Types and signatures

POC copy-then-edit (after `可以开始实现` only) keeps the Trunk call convention:

```text
float DiskHNSW::pqDistance(const float* query, uint32_t node_id_new) const;
void DiskHNSW::buildPqDistTable(const float* query);
```

D1 MUST NOT change these signatures. `buildPqDistTable` stays as-is (already SIMD).
Distance return MUST match the scalar table-lookup path bitwise, or differ by ≤1e-6
with Recall@10 unchanged.

## Config / env / flags

实验面旋钮（与 cfg / Measure 对齐处写指针）：

| name | meaning | default |
|------|---------|---------|
| `HNSW_PQ_SIMD` | Opt-in D1 SIMD gather path inside topic copy of `pqDistance` | `0` (off; scalar table lookup) |
| `cfg-m24-ef60` | Golden Config C bind (not an env) | see PERF_BASELINE.md |

Default off preserves current behavior until the implementation hop enables the flag
for A/B. No new Trunk `API-*`.

## Errors and invariants

- [[CHR-006]] Recall@10 ≥ 95% MUST hold on the D1 path.
- `pqDistance` results MUST be bitwise-equal to scalar, or abs error ≤ 1e-6 **and** Recall@10 unchanged.
- Failure → keep scalar reduction order or abandon that SIMD reduction (DESIGN failure modes).
- No new exception types; existing load/search errors unchanged.

## Threading / lifetime

Unchanged vs Trunk `DiskHNSW`: `pq_dist_table_` is per-query thread-local table
(`M=32 × ksub=256`). D1 gather is inside the existing per-query / per-thread search
path. No new shared mutable state. Copy-then-edit files live under
`poc/hotspot-optimization/src/` after `可以开始实现` only.

## Draft API-* map

| draft id | this surface | note |
|----------|--------------|------|
| N/A | `DiskHNSW::pqDistance` | no new Trunk API; POC-only opt-in flag |
<!-- ndf:gate-slice end=interface_contract -->
