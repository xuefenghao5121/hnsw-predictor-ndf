# POC Measurement R2 — hierarchical-vamana beam+R0 sweep @ α=1.2

> topic: hierarchical-vamana | task: poc_measurement | date: 2026-08-25
> bind: vs=bl-trunk-d0ae5dd, config=cfg-sla-ef100, measure=poc/hierarchical-vamana/scripts/run_poc_measure.sh
> protocol: VER-001 sustained (official 10K pool, 15 rounds × 1000, seed=42) + VER-003 cgroup v2 512MB / 16T
> sweep: beam ∈ {32,64,128} @ R0=32 and R0 ∈ {24,32,40} @ beam=64, fixed HV_M=16 HV_RUP=16 HV_ALPHA=1.2 HV_ROUNDS=3 HV_SEED=42
> raw logs: run_poc_measure-512mb-16t-r2-*.log + build-r2-*.log

## Results (SIFT1M @ 512MB cgroup @ 16T, VER-001 sustained)

### beam axis (R0=32 fixed)

| beam | L0 edges | L0 avg deg | RSS init | Recall@10 | agg QPS | steady QPS (R15) | RSS end | L0 build |
|-----:|---------:|-----------:|---------:|----------:|--------:|-----------------:|--------:|---------:|
| 32 | 26,244,126 | 26.24 | 171 MB | 97.02% | 6210.4 | 10051.2 | 367 MB | 72.3 s |
| 64 | 29,638,786 | 29.64 | 175 MB | **98.00%** | 6159.1 | 9599.4 | 371 MB | 135.9 s |
| 128 | 31,048,095 | 31.05 | 177 MB | 97.86% | 6130.1 | 9584.3 | 372 MB | 248.8 s |

### R0 axis (beam=64 fixed)

| R0 | L0 edges | L0 avg deg | RSS init | Recall@10 | agg QPS | steady QPS (R15) | RSS end | L0 build |
|--:|---------:|-----------:|---------:|----------:|--------:|-----------------:|--------:|---------:|
| 24 | 23,250,673 | 23.25 | 163 MB | 95.87% | 6367.0 | 10507.5 | 358 MB | 107.4 s |
| 32 | 29,638,786 | 29.64 | 175 MB | **98.00%** | 6159.1 | 9599.4 | 371 MB | 135.9 s |
| 40 | 34,640,174 | 34.64 | 185 MB | 98.95% | 6047.8 | 8953.9 | 381 MB | 161.9 s |

### Reference baselines

| ref | Recall@10 | agg QPS | steady QPS | RSS init | RSS end |
|-----|----------:|--------:|-----------:|---------:|--------:|
| bl-trunk-d0ae5dd (hnswlib) | 96.00% | 4330.9 | 6448.0 | 157 MB | 352 MB |
| R1 α=1.2 (beam=64/R0=32) | 98.00% | 6052.2 | 9214.9 | 175 MB | 371 MB |

## Interpretation

1. **beam (32→128, R0=32 fixed): negligible effect.** Recall 97.02→98.00→97.86%, agg QPS
   6210.4→6159.1→6130.1, RSS 367→371→372 MB. Higher beam adds L0 edges (26.24M→31.05M) and build
   time (~linear: 72s→249s) without recall/QPS gain. beam=64 (R1 default) is the best-recall point
   and a good cost/benefit; beam=32 is slightly faster/leaner at −0.98 pp recall.

2. **R0 (24→40, beam=64 fixed): dominant monotonic knob.** R0↑ ⇒ edges↑, recall↑, QPS↓, memory↑.
   R0=32 is the operating point (Recall 98.00%, QPS/memory balanced). R0=40 reaches 98.95%
   (+0.95 pp) at −1.8% agg QPS, +10 MB RSS, +4.99M edges — an optional recall-margin config. R0=24
   is the leanest (358 MB end, best agg QPS 6367.0) but recall 95.87% leaves thin ≥95% margin.

3. **Operating point unchanged: beam=64, R0=32, α=1.2.** Both sweeps confirm R1's choice: recall
   98.00% (+2.0 pp vs trunk 96.00%), agg QPS ~+42% vs trunk (4330.9), within 512 MB budget.

## Variance note

R2 center point (beam=64/R0=32) agg QPS 6159.1 matches R1 α=1.2 re-measure (6052.2) within ~2% —
both warm-session values, ~30% above R0's cold-cache 4653.9. Recall@10 stable at 98.00%. The
beam/R0 sweeps are internally consistent (single session). Known teardown defect unchanged:
`benchmark_sustained` aborts (`terminate called without an active exception`) after printing all
15 rounds + aggregate + CSV_AGG; measured values are complete and valid.
