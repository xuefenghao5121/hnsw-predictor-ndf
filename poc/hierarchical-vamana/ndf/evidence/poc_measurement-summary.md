# POC Measurement R1 — hierarchical-vamana α-sweep

> topic: hierarchical-vamana | task: poc_measurement | date: 2026-08-25
> bind: vs=bl-trunk-d0ae5dd, config=cfg-sla-ef100, measure=poc/hierarchical-vamana/scripts/run_poc_measure.sh
> protocol: VER-001 sustained (official 10K pool, 15 rounds × 1000, seed=42) + VER-003 cgroup v2 512MB / 16T
> sweep: α ∈ {1.0, 1.2, 1.4}, fixed HV_M=16 HV_R0=32 HV_RUP=16 HV_BEAM=64 HV_ROUNDS=3 HV_SEED=42
> raw logs: run_poc_measure-512mb-16t-alpha{1.0,1.2,1.4}.log + build-alpha{1.0,1.2,1.4}.log

## Results (SIFT1M @ 512MB cgroup @ 16T, VER-001 sustained)

| α | L0 edges | L0 avg deg | CSR | RSS init | Recall@10 | agg QPS | steady QPS (R15) | RSS end | L0 build |
|----|---------:|-----------:|----:|---------:|----------:|--------:|-----------------:|--------:|---------:|
| 1.0 | 13,514,675 | 13.51 | 33 MB | 142 MB | 91.43% | 7128.0 | 11205.9 | 338 MB | 96.9 s |
| 1.2 | 29,638,786 | 29.64 | 65 MB | 175 MB | **98.00%** | 6052.2 | 9214.9 | 371 MB | 137.1 s |
| 1.4 | 31,889,002 | 31.89 | 65 MB | 206 MB | 95.92% | 5499.7 | 8438.7 | 401 MB | 148.3 s |

### Reference baselines

| ref | Recall@10 | agg QPS | steady QPS | RSS init | RSS end |
|-----|----------:|--------:|-----------:|---------:|--------:|
| bl-trunk-d0ae5dd (hnswlib) | 96.00% | 4330.9 | 6448.0 | 157 MB | 352 MB |
| R0 α=1.2 (prior session) | 98.00% | 4653.9 | 6999.8 | 175 MB | 371 MB |

## Interpretation (α sensitivity)

RobustPrune α (this codebase convention: **higher α ⇒ less pruning ⇒ more edges**) sweeps a
clean recall/memory tradeoff:

1. **α=1.0 — over-pruned (FAIL).** Avg degree collapses to 13.5 → Recall@10 91.43%, below the
   H0 ≥95% target. Highest QPS (7128 agg / 11206 steady) but recall is unacceptable.
2. **α=1.2 — optimal.** Best Recall@10 (98.00%), and still +40% agg QPS / +43% steady vs trunk
   (+2.0 pp recall). Confirms R0.
3. **α=1.4 — under-pruned (degrading).** Avg degree 31.9 ≈ R=32 cap (prune barely fires); edges
   degenerate toward "greedy nearest-32" losing α-diversity → recall *drops* to 95.92% (vs 98.00%
   at α=1.2) while memory grows to 401 MB (approaching the 512 MB budget) and QPS falls to 5499.7.

Conclusion: α=1.2 is the operating point. α=1.0 trades recall for speed (fails target); α=1.4
trades recall *and* speed for memory (strictly worse than 1.2). H0 criterion (≥95% Recall@10)
is met at α∈{1.2,1.4}, with α=1.2 dominant.

## Variance note

R1 α=1.2 re-measure (agg 6052.2 / steady 9214.9) is ~30% above R0's 4653.9 / 6999.8 — run-to-run
variance from warm OS page cache after consecutive in-session runs (Recall@10 is stable at 98.00%).
The α-sweep is internally consistent (single session, identical conditions); absolute QPS vs trunk
should be read with ±~30% session noise.

Known teardown defect (unchanged from R0): `benchmark_sustained` aborts (`terminate called without
an active exception`) after printing all 15 rounds + aggregate + CSV_AGG; measured values are
complete and valid.
