# Topic: SSD Parallelism I/O Optimization (inspired by VLDB 2025)

> status: promoted
> track: poc
> created: 2026-08-10
> baseline_trunk_sha: 434c6f5
> baseline_status: current
> source_paper: "Turbocharging Vector Databases using Modern SSDs", Shim et al., PVLDB 18(11):4710-4722, 2025
> depends_on_topics: (none, but informed by rejected io-pipelining DEC-071 and mmap-budget-shift DEC-094)

## explore_surface

- **目标**: 借鉴论文 io_uring CQE peeking + 向量共置技术，探索 DiskHNSW I/O 路径优化
- **不改动**: Trunk `src/`、`include/`、`tests/`（[[CON-POC-001]] POC 隔离）
- **代码落点**: `poc/ssd-parallelism-io/` only
- **与已 rejected 方向的区别**:
  - vs io-pipelining (DEC-071): pipe_ring_ 是用户态预取，与 WILLNEED 重叠无收益。本 topic 用 io_uring 替代 pread，利用 CQE 完成顺序
  - vs mmap-budget-shift (DEC-094): mmap 改数据加载方式。本 topic 改 I/O 调度策略
  - vs data-layout-optimization: BFS 重排 ceiling ~4%。本方向 B 测试聚类重排

## 背景

### 论文三大技术

1. **io_uring 并行邻居检索**: 异步批量读取 uncached 邻居页，替代阻塞 read
2. **流水线距离计算 (pg_async_iou)**: I/O 发出后立即算 cached 邻居，CQE 按到达顺序处理（非批量屏障）
3. **局部性保持共置**: 预聚类共访向量到相同 page

### DiskHNSW 现状

- I/O 路径: WILLNEED_BG (fadvise 后台预取) + pread (阻塞按序读取)
- 已有 BFS 重排 (DEC-064) 提供空间局部性
- 已有 io_uring 支持 (FINE_PREAD=0)，但多线程下退化为 pread

### 关键差异

论文优化 pgvector（阻塞 read + PostgreSQL buffer cache），我们已有 WILLNEED_BG + pread。
DEC-071 证明用户态预取与 WILLNEED 重叠无收益。但 CQE peeking（按完成顺序处理）是没做过的。

## R0 计划

### 方向 A: io_uring CQE peeking 替代 pread

**假设**: pread 按固定顺序阻塞，SSD 通道间完成时间不对称。改用 io_uring + CQE peeking 可减少 CPU 空闲。

**与 DEC-071 的关键区别**:
- DEC-071: pipe_ring_ 预取与 WILLNEED 重叠 -> 无收益
- 本方向: 用 io_uring read 替代 pread，CQE 完成后立即计算距离（非批量屏障）
- WILLNEED 仍然作为 fadvise 预热，但数据读取从 pread 改为 io_uring

**实现**: 拷贝 `src/core/disk_hnsw.cpp` + 相关头到 `poc/ssd-parallelism-io/`，patch fine rerank 路径：
- A (baseline): WILLNEED_BG + pread（现有路径）
- B (experimental): WILLNEED_BG + io_uring read + CQE peeking

### 方向 B: 向量共置（聚类重排）

**假设**: BFS 重排按图结构顺序。k-means 聚类重排可提升 block_cache 命中率。

**实现**: 离线工具对 SIFT1M 向量做 k-means 聚类，按簇序重排 vecblocks。
- A (baseline): BFS order（现有）
- B (experimental): k-means cluster order

**风险**: 改变 vecblock 顺序可能破坏 BFS 图遍历的 cache 局部性。需重建 graph + bfs。

## 验证计划

- 测试脚本: `scripts/run_sustained.sh --config cfg-m24-ef60`（金标载体）
- 测试标准: CON-SLA-020 sustained + CON-SLA-019 禁预热 + CON-SLA-014 严格 cgroup
- 配置: Config C (M=24, EF=60), 256MB, 1T, 15轮×1000q, seed=42
- 基线: bl-trunk-golden-434c6f5 (agg 1,450 / steady 1,702 / recall 96.60%)
- recall ≥ 95%
- A/B 唯一差异: I/O 路径或数据排布

## 参考条款

- BEH-024 (L4 page cache management)
- BEH-027 (WILLNEED BG)
- BEH-033 (Fine rerank pipeline)
- DEC-070 (WILLNEED promote)
- DEC-071 (io-pipelining REJECTED)
- DEC-094 (mmap-budget-shift REJECTED)
- CON-SLA-014 / CON-SLA-019 / CON-SLA-020
- CON-GOLDEN-001
