# Perf Baseline: bfs-cluster

> baseline: bl-trunk-golden-7ee4ee2
> trunk_sha: ${TRUNK_SHA}
> protocol: CON-SLA-020 sustained, CON-SLA-014 strict cgroup, CON-SLA-019 禁预热
> config: Config C (M=24, EF=60), SIFT1M

## Golden (BFS default, pread)

| 线程 | cgroup | agg QPS | steady QPS | Recall |
|------|--------|:---:|:---:|:---:|
| 1T | 256MB | 1,442 | 1,635 | 96.60% |
| 16T | 256MB | 3,451 | 4,426 | 96.60% |

## Golden (cluster k=1024, pread, BEH-037)

| 线程 | cgroup | agg QPS | steady QPS | Recall |
|------|--------|:---:|:---:|:---:|
| 1T | 256MB | 1,812 | 2,056 | 96.60% |
| 16T | 256MB | 5,223 | 7,018 | 96.60% |

## Measure

- QPS (agg + steady), Recall@10
- vs pure k=1024 Δ%
- cluster switches per block
- intra-cluster graph edge density
