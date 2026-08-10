# Baseline: bl-trunk-golden-7ee4ee2

> baseline_id: bl-trunk-golden-7ee4ee2
> trunk_sha: 7ee4ee2b0af04feb154abcfd528feabe1557e073
> short_sha: 7ee4ee2
> status: current
> measured: 2026-08-10
> protocol: [[CON-SLA-020]] sustained, [[CON-SLA-014]] strict cgroup, [[CON-SLA-019]] 禁预热
> dataset: SIFT1M
> query: 官方 10K pool, 15 rounds × 1000, seed=42
> hardware: Intel i7-13700 (16C/24T), 32GB DDR4, NVMe SSD
> configs: cfg-m24-ef60
> clause: [[CON-GOLDEN-001]]
> process: [[META-006]]
> promotes: BEH-036 (CQE peeking), BEH-037 (cluster vecblock reorder)

> Previous: bl-trunk-golden-68059a6

## Config C: M=24, EF=60

### BFS default (pread, FINE_PREAD=1)

| 线程 | cgroup | agg QPS | steady QPS | Recall@10 |
|------|--------|:---:|:---:|:---:|
| 1T | 256MB | **1,442** | **1,635** | 96.60% |
| 16T | 256MB | **3,451** | **4,426** | 96.60% |
| 1T | 512MB | **1,848** | **2,057** | 96.59% |
| 16T | 512MB | **6,777** | **12,873** | 96.59% |

### CQE peeking (BEH-036, FINE_PREAD=0)

| 线程 | cgroup | agg QPS | steady QPS | Recall@10 |
|------|--------|:---:|:---:|:---:|
| 1T | 256MB | **1,496** | **1,711** | 96.60% |
| 4T | 256MB | **3,495** | **4,578** | 96.60% |
| 16T | 256MB | **3,392** | **4,721** | 96.60% |

### Cluster-sorted vecblocks (BEH-037, k=1024, pread)

| 线程 | cgroup | agg QPS | steady QPS | Recall@10 |
|------|--------|:---:|:---:|:---:|
| 1T | 256MB | **1,812** | **2,056** | 96.60% |
| 16T | 256MB | **5,223** | **7,018** | 96.60% |
| 1T | 512MB | **2,317** | **2,711** | 96.59% |
| 16T | 512MB | **9,770** | **17,625** | 96.59% |
