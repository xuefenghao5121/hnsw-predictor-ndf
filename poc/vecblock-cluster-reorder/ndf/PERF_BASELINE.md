# Perf Baseline: vecblock-cluster-reorder

> baseline: bl-trunk-golden-68059a6
> trunk_sha: 97ce18e
> protocol: CON-SLA-020 sustained, CON-SLA-014 strict cgroup, CON-SLA-019 禁预热
> config: Config C (M=24, EF=60), SIFT1M

## Golden (pread default)

| 线程 | cgroup | agg QPS | steady QPS | Recall |
|------|--------|:---:|:---:|:---:|
| 1T | 256MB | 1,438 | 1,646 | 96.60% |
| 16T | 256MB | 3,483 | 4,492 | 96.60% |

## Golden (CQE peeking, FINE_PREAD=0)

| 线程 | cgroup | agg QPS | steady QPS | Recall |
|------|--------|:---:|:---:|:---:|
| 1T | 256MB | 1,496 | 1,711 | 96.60% |
| 4T | 256MB | 3,495 | 4,578 | 96.60% |
| 16T | 256MB | 3,392 | 4,721 | 96.60% |

## Measure

- QPS (agg + steady), Recall@10
- I/O pages per query (PROFILE_FINE)
- 聚类纯度 vs 页数 vs QPS 曲线
