# Proposal: POC - 借鉴 Turbocharging Vector Databases (VLDB 2025) 的 I/O 优化技术

> track: poc
> status: draft
> date: 2026-08-10
> topic: ssd-parallelism-io
> affects: BEH-024, BEH-027, BEH-033
<!-- ndf: depends-on=BEH-024,BEH-027,DEC-070,DEC-071,DEC-094 -->

## 论文信息

**标题**: Turbocharging Vector Databases using Modern SSDs
**作者**: Joobo Shim, Jaewon Oh, Hongchan Roh, Jaeyoung Do, Sang-Won Lee (Seoul National University)
**发表**: PVLDB 18(11): 4710–4722, July 2025
**DOI**: 10.14778/3749646.3749724
**代码**: https://github.com/FlashSQL/io-optimized-pgvector

## 论文核心内容

### 三大优化技术

| # | 技术 | 原理 | 代码分支 |
|---|------|------|---------|
| 1 | **io_uring 并行邻居检索** | 用 io_uring SQ/CQ 异步批量读取 uncached 邻居页，替代逐页阻塞 pread | `pg_iou` |
| 1b | **流水线距离计算** | I/O 发出后立即开始计算 cached 邻居距离，CQE 完成后按到达顺序处理（非批量屏障） | `pg_async_iou` |
| 2 | **空间感知插入重排** | 动态调整插入顺序，相似向量连续插入以提升 cache 复用 | §5 |
| 3 | **局部性保持共置** | 预聚类可能被共访的向量，索引构建时放入相同 index page | §6 |

### 关键结果

- 最高 **11.1×** 查询吞吐提升
- **3.23×** cache 命中率提升
- **98.4%** 索引构建时间减少
- 基于 pgvector 0.8.0 + PostgreSQL 17

### 论文识别的三个低效点

1. **低时间局部性**: 连续 query 访问不相关向量，cache 复用差
2. **低空间局部性**: HNSW 图遍历时每跳访问不同 page，~1 page/node
3. **SSD 并行度未利用**: 阻塞式 I/O 无法利用 NVMe 多通道并行

## 与 DiskHNSW 的关联分析

### 已有工作（已关闭）

| 方向 | 结论 | DEC |
|------|------|-----|
| io-pipelining (pipe_ring_) | REJECTED: WILLNEED 已覆盖 I/O 与 CPU 并行 | DEC-071 |
| speculative-prefetch | REJECTED: major fault 仅 3%，disk I/O 不是瓶颈 | DEC-093* |
| mmap-budget-shift | REJECTED: page cache thrashing | DEC-094 |
| data-layout-optimization | REJECTED: ceiling ~4% QPS | DEC-093* |

### 论文技术 1 (io_uring) vs 我们已有结论

**关键差异**: 论文的优化目标是 **pgvector（PostgreSQL buffer cache）**，我们的优化目标是 **DiskHNSW（自定义 block_cache + pread + WILLNEED）**。

| 维度 | pgvector (论文) | DiskHNSW (我们) |
|------|-----------------|-----------------|
| I/O 路径 | PostgreSQL buffer cache -> read() | pread() + fadvise(WILLNEED) |
| 并行 I/O | 无（阻塞 read） | WILLNEED_BG 后台线程（无锁 SPSC） |
| 完成顺序 | 批量屏障 | pread 固定顺序 |
| io_uring | 无 | 有（FINE_PREAD=0 时），但多线程下退化为 pread |

**DEC-071 教训**: io-pipelining（pipe_ring_）在 WILLNEED 已启用时无收益，因为两者在同一时机触发 I/O 预取。

**但论文的 pg_async_iou 有一个我们没做的关键点**:
- **按完成顺序处理**（peeking CQE）而非批量屏障
- 我们的 pread 是固定顺序阻塞，无法先到先算
- 论文指出 SSD 通道间完成时间不对称，批量屏障浪费 CPU

### 论文技术 2/3 (插入重排 + 共置) vs 我们

| 维度 | pgvector (论文) | DiskHNSW (我们) |
|------|-----------------|-----------------|
| 数据布局 | PostgreSQL index pages | BFS-ordered vecblocks (64KB) |
| 局部性优化 | 插入时重排 + 共置聚类 | BFS 重排（构建时一次性） |
| 动态性 | 支持动态插入 | 静态数据集 |

我们已有 BFS 重排（[[DEC-064]]）提供空间局部性。论文的共置是更激进版本（聚类而非 BFS）。

## R0 探索方向

### 方向 A: io_uring 完成顺序优化（最有价值）

**假设**: 当前 WILLNEED_BG + pread 路径中，pread 按固定顺序阻塞。如果改用 io_uring + CQE peeking，按完成顺序计算距离，可减少 CPU 空闲。

**与 DEC-071 的区别**:
- DEC-071 的 pipe_ring_ 是**用户态预取**（io_uring 读到 pipe buffer），与 WILLNEED 重叠
- 本方向是**用 io_uring 替代 pread**，利用 CQE 完成顺序而非批量屏障
- 关键：WILLNEED 仍然是 fadvise 预热，但实际数据读取从 pread 改为 io_uring read

**R0 测试**: A (WILLNEED_BG + pread) vs B (WILLNEED_BG + io_uring CQE peeking)

### 方向 B: 向量共置（BFS + 聚类增强）

**假设**: 当前 BFS 重排按图结构邻居顺序排列。如果改为先聚类（k-means / IPC），同簇向量放入相邻 vecblocks，可提升 block_cache 命中率。

**与 data-layout-optimization 的区别**:
- data-layout POC 测试了 BFS 重排 vs 原始顺序，ceiling ~4%
- 本方向测试**聚类重排**（更激进，可能改变图结构）

**风险**: 改变 vecblock 顺序可能影响 BFS 图遍历的 cache 局部性

**R0 测试**: A (BFS order) vs B (k-means cluster order)

## 协议

- 测试标准: **CON-SLA-020** sustained（金标）
- 测试脚本: `scripts/run_sustained.sh --config cfg-m24-ef60`（[[CON-SLA-020]] 金标载体）
- 隔离: [[CON-SLA-014]] 严格 cgroup
- 禁预热: [[CON-SLA-019]]
- 配置: Config C (DEC-087: M=24, EF=60), 256MB, 1T, 15轮 × 1000q, seed=42
- 基线: bl-trunk-golden-434c6f5 (agg 1,450 / steady 1,702 / recall 96.60%)
- recall ≥ 95%

## 不改的项

- 不改 Trunk `src/`、`include/`、`tests/`（POC 隔离 [[CON-POC-001]]）
- 不改 SLA 阈值
- 不改现有 API 参数默认值

## 参考条款

- BEH-024 (L4 page cache management)
- BEH-027 (WILLNEED BG)
- BEH-033 (Fine rerank pipeline)
- DEC-070 (WILLNEED promote)
- DEC-071 (io-pipelining REJECTED)
- DEC-094 (mmap-budget-shift REJECTED)
- CON-SLA-014 / CON-SLA-019 / CON-SLA-020
- CON-GOLDEN-001
