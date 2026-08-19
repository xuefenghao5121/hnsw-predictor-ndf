# Topic: page-packer

> ndf_topic: page-packer
> status: rejected
> created: 2026-08-10
> closed: 2026-08-18
> explore_surface: spec/20-behavior/vecblock-layout
> depends_on_topics: vecblock-cluster-reorder (promoted)
> baseline_status: current
> baseline_trunk_sha: 9df8b74
> baseline_protocol: CON-SLA-020 sustained, CON-SLA-014 strict cgroup, CON-SLA-019 禁预热
> reference: BEH-037 (cluster vecblock), DEC-018 (page shuffle)
> selected_decision: reject
> rejects_dec: DEC-100
> archive: spec/archive/2026-08/poc-page-packer/

## Hypothesis

Cluster sort (BEH-037) 将相似向量集中到同一 block，但 4KB 页内（8 vectors）
仍含 ~3 个不同 cluster。贪心页面打包：对每 cluster 段内用 graph adjacency
贪心分配页 → 每页 graph neighbors 最大化 → 更高页命中率 → 更高 QPS。

两步:
1. within-block cluster sort (existing)
2. per-cluster-segment greedy page packing (new)

## Directions

### R0: 两步 pipeline A/B
- A: cluster sort only (BEH-037, k=1024)
- B: cluster sort + page packing
- Measure: pages/query, QPS, recall

## Perf Baseline

见 ndf/PERF_BASELINE.md
