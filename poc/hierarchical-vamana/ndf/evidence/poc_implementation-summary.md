# POC Implementation — hierarchical-vamana R0 evidence

> topic: hierarchical-vamana | task: poc_implementation | date: 2026-08-25
> bind: vs=bl-trunk-d0ae5dd, config=cfg-sla-ef100, measure=poc/hierarchical-vamana/scripts/run_poc_measure.sh
> protocol: VER-001 sustained (official 10K pool, 15 rounds × 1000, seed=42) + VER-003 cgroup v2 512MB
> raw log: run_poc_measure-512mb-16t.log

## What was built

Layered Vamana builder (`poc/hierarchical-vamana/build/vamana_build.cpp`):
- HNSW geometric level assignment (M=16, seed=42) → max_level=4, 62,778 upper nodes
- Per-layer Vamana: GreedySearch (beam=64) + RobustPrune (α=1.2), 3 refinement rounds,
  OpenMP double-buffered (race-free)
- Exports `GraphStructure` (same format as Trunk `extract_graph`), feeding the unchanged
  Trunk `bfs_reorder` / `write_blocks` / `write_blocks_veconly` / `gen_route` pipeline
  and the unchanged DiskHNSW search + PQ (`pqco_sift1m_M32_correct.bin`, graph-independent).

Parameters: HV_M=16 HV_R0=32 HV_RUP=16 HV_BEAM=64 HV_ALPHA=1.2 HV_ALPHA2=0 HV_ROUNDS=3 HV_SEED=42

## Graph statistics

| metric | value |
|--------|-------|
| nodes | 1,000,000 |
| max_level | 4 |
| upper-layer nodes (level>0) | 62,778 |
| L0 edges | 29,638,786 (avg degree 29.64) |
| L0 CSR compact | 62 MB (delta+varint, 1.8× vs raw 116 MB) |
| build wall time | 132 s (L0) / 2:12 total |

## Measurement (cfg-sla-ef100, SIFT1M @ cgroup 512MB @ 16T)

| metric | hierarchical-vamana | bl-trunk-d0ae5dd | Δ |
|--------|--------------------:|-----------------:|----:|
| Recall@10 | **98.00%** | 96.00% | **+2.00 pp** |
| agg QPS | **4653.9** | 4330.9 | **+7.5%** |
| steady QPS (R15) | **6999.8** | 6448.0 | **+8.6%** |
| Round 1 QPS | 1123.1 | 1084.0 | +3.6% |
| Ramp-up | 523.2% | 494.8% | — |
| RSS after init | 175 MB | 157 MB | +18 MB (+11%) |
| RSS end-of-run | 371 MB | 352 MB | +19 MB (+5%) |

## Interpretation

H0 supported on R0: Vamana RobustPrune (α=1.2) replaces hnswlib's degree-capped greedy
edges with more angularly-diverse long-range edges. Effect at matched protocol:
- **+2.0 pp recall** (98.00% vs 96.00%) — better edge diversity covers more of the manifold.
- **+7.5% agg QPS / +8.6% steady QPS** — shorter/cleaner navigation paths (H1/H2).
- Cost: slightly higher resident memory (+18 MB RSS) because diverse long-range edges
  delta-compress worse under BFS reorder (62 MB CSR vs ~47 MB for hnswlib's ~32M localized
  edges). Memory still within the 512 MB cgroup budget (no OOM).

Known teardown defect: `benchmark_sustained` aborts (`terminate called without an active
exception`) after printing all 15 rounds + aggregate + CSV_AGG — identical to the documented
baseline behavior; measured values are complete and valid.
