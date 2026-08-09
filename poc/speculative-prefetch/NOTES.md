# Notes: Speculative Prefetch POC

> 创建: 2026-08-09
> Trunk SHA: 3e98f3e
> Status: EXPLORING — R0 done, R1/R2 方向已定

## 历史教训

**R0 第一/二次**: 测量环境不规范（无 cgroup / 手动拼环境）。**废弃。**
**R0 第三次**: 基于金标脚本环境。**有效。**

## R0: Gold Standard Profiling — DONE (2026-08-09)

配置 A (256MB 1T EF=100, 15轮×1000q, cgroup drop_caches):

**性能**: agg=1052 QPS / steady=1149 QPS / 950 us per query

**时间分解**:
- Graph search (含 block I/O): 950 us (100%)
- FineRerank: 0.04 us (可忽略)

**Disk I/O 证据**:
- Page faults: 9.0/query → ~36KB disk read/query
- 估算 disk I/O: ~449 us (47% of latency)
- LLC miss rate: 58.1% (5,087/query)
- L1 miss rate: 2.2% (PQ ADC 在 cache)

**结论**: disk I/O 占 ~47%, CPU 计算 + memory latency 占 ~53%。
瓶颈在 graph search 内部的 block loading (cache miss → 同步磁盘读取)。

Evidence: `ndf/evidence/r0-gold-standard-20260809.md`

## 下一步方向

R1: graph_prefetcher_ 自适应深度预取 (block-level speculative prefetch)
- 当前: 固定 1-hop
- 改进: 高 cache miss 时做 2-hop
- 借鉴: VelesDB 的 `calculate_prefetch_distance()` 自适应理念

R2: block layout page locality 分析
- 分析 block 内 page-level access pattern
- 评估是否需要重排
