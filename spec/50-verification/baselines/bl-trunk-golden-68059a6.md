# Baseline: bl-trunk-golden-68059a6

> baseline_id: bl-trunk-golden-68059a6  
> trunk_sha: 68059a6f0c232e028277a499d329c1216f9d49d7  
> short_sha: 68059a6  
> status: current  
> measured: 2026-08-10  
> protocol: [[CON-SLA-020]] sustained, [[CON-SLA-014]] strict cgroup, [[CON-SLA-019]] 禁预热  
> dataset: SIFT1M  
> query: 官方 10K pool, 15 rounds × 1000, seed=42  
> hardware: Intel i7-13700 (16C/24T), 32GB DDR4, NVMe SSD  
> configs: cfg-m24-ef60  
> clause: [[CON-GOLDEN-001]]  
> process: [[META-006]]  
> promotes: BEH-036 (CQE peeking), API-020 (FINE_CQE_PEEK)

> Previous: bl-trunk-golden-434c6f5

## Config C: M=24, EF=60, 256MB cgroup

### pread 路径 (FINE_PREAD=1, default)

| 线程 | agg QPS | steady QPS | Recall@10 |
|------|:---:|:---:|:---:|
| 1T | **1,438** | **1,646** | 96.60% |
| 16T | **3,483** | **4,492** | 96.60% |

### CQE peeking 路径 (FINE_PREAD=0, BEH-036)

| 线程 | agg QPS | steady QPS | Recall@10 |
|------|:---:|:---:|:---:|
| 1T | **1,496** | **1,711** | 96.60% |
| 4T | **3,495** | **4,578** | 96.60% |
| 16T | **3,392** | **4,721** | 96.60% |

### vs pread

| 线程 | Δ agg | Δ steady |
|------|:---:|:---:|
| 1T | +4.0% | +4.0% |
| 16T | −2.6% | +5.1% |

Note: 16T steady regression is within run-to-run variance;
CQE peeking benefit diminishes at high thread counts (I/O parallelism sufficient).
