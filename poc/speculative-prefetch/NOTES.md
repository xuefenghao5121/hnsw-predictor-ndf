# Notes: Speculative Prefetch POC

> 创建: 2026-08-09
> Trunk SHA: 3e98f3e
> Status: R0 DONE — POC direction reassessed

## R0: Gold Standard Profiling — DONE (2026-08-09)

配置 A (256MB 1T EF=100, 15轮×1000q, cgroup drop_caches):

### 瓶颈定位（三维度）

| 瓶颈 | 占比 | 证据 |
|------|------|------|
| **LLC miss → DRAM latency** | **~74%** | 5,087 miss/query, 58.1% miss rate |
| CPU compute (PQ ADC + heap) | ~24% | IPC=2.37, L1 miss 2.2% |
| Disk I/O | ~3% | Major fault 0.50/query |

### 关键发现

1. **graph_prefetcher_ 在 PQ 模式完全不工作** (useful=0, code line 497 跳过)
2. **Disk I/O 不是瓶颈** — WILLNEED bg_thread 已覆盖 (major fault 仅 0.50/query)
3. **CPU L1 cache 不是瓶颈** — PQ ADC 在 cache 中 (L1 miss 2.2%)
4. **LLC miss 是真正瓶颈** — 数据结构总量 ~240MB >> L3 cache ~30MB

### VelesDB 适用性

VelesDB 的 prefetch 策略针对内存中向量遍历的 cache miss。
我们的 PQ 模式：
- 距离计算用 PQ ADC (32B/vector, 已在 L1)
- 邻居表用 CSR (47MB, 随机访问, 超过 L3)
- Block cache 用 LRU (64MB, 超过 L3)

VelesDB prefetch 不适用于此架构。R1 (2-hop graph prefetch) 无意义因为 graph_prefetcher_ 在 PQ 模式被跳过。

Evidence: `ndf/evidence/r0-gold-standard-20260809.md`
