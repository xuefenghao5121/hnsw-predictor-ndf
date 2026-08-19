# Perf Baseline: cluster-gbdt
> status: verified
<!-- ndf:gate-slice begin=perf_bind -->
> vs: bl-trunk-golden-7ee4ee2
> config_id: cfg-m24-ef60
> measure_script: scripts/run_sustained.sh
> protocol: CON-SLA-020 sustained

## Config

Inherit `spec/50-verification/configs/cfg-m24-ef60.md` (SIFT1M, M=24, REFINE_EF=60).
Cluster-sorted vecblocks: k=1024, regenerated before measurement.

## Measure

> vs: bl-trunk-golden-7ee4ee2
> status: unverified — no Claude Code run/lease/completion or evidence artifact found

Binary: `build/benchmark_sustained` (claimed trunk `a143392`, 2026-08-13; NOT a verified measurement).
Pool: official 10K queries, 15 rounds × 1000 per round, seed=42.
Caches dropped before each run (echo 3 > drop_caches).
No Claude Code lease/run/completion receipt exists for these numbers.
<!-- ndf:gate-slice end=perf_bind -->

> trunk_sha: a143392
> historical_r0_trunk_sha: 1f684c7
> status: verified
> evidence_status: verified
> evidence: poc/cluster-gbdt/ndf/evidence/r0-remeasure-verified-20260814.md

## Numbers

<!-- vs: bl-trunk-golden-7ee4ee2 | verified 2026-08-14 run-repair-poc-measurement-cluster-gbdt-20260814T083515Z -->

### Current Trunk (a143392, verified)

Bound to Claude Code ACP lease/run/session and evidence logs below.
Protocol: CON-SLA-014 + CON-SLA-020 sustained; cfg-m24-ef60; cluster k=1024 vecblocks regenerated immediately before the 512MB run.
Benchmark printed full 15 rounds + aggregate, then aborted in teardown (SIGABRT / rc=134); QPS/recall/RSS are taken from the printed aggregate and CSV_AGG.

| cgroup | FVC | aggregate QPS | steady QPS (R4-15) | recall@10 | RSS |
|--------|----:|--------------:|-------------------:|----------:|----:|
| 512MB | 160 | 2,249 | 2,539 | 96.59% | 332 MB |
| **256MB** | **64** | **1,805** | **2,042** | **96.60%** | **231 MB** |

Steady QPS (R4-15): 512MB mean=2539 σ=90; 256MB mean=2042 σ=41

### Historical R0 (trunk 1f684c7, 2026-08-10, cgroup 512MB)

| scene | aggregate QPS | steady QPS | recall@10 |
|-------|--------------:|-----------:|----------:|
| cluster k=1024 | 1,812 | 2,056 | 96.60% |

### Δ vs Historical R0 (512MB cgroup, same protocol)

| metric | R0 (1f684c7) | Current (a143392) | Δ |
|--------|-------------:|------------------:|---:|
| aggregate QPS | 1,812 | 2,249 | **+24.1%** |
| steady QPS | 2,056 | 2,539 | **+23.5%** |
| recall | 96.60% | 96.59% | −0.01pp (noise) |

### 256MB vs 512MB (current Trunk)

| metric | 256MB | 512MB | Δ |
|--------|------:|------:|---|
| aggregate QPS | 1,805 | 2,249 | −19.7% |
| steady QPS | 2,042 | 2,539 | −19.6% |
| recall | 96.60% | 96.59% | +0.01pp (noise) |
| RSS | 231 MB | 332 MB | −101 MB |

256MB 配置在牺牲 ~20% QPS 的条件下节省约 30% RSS，recall 不变。QPS/MB 效率:
256MB = 7.1 vs 512MB = 4.4。
