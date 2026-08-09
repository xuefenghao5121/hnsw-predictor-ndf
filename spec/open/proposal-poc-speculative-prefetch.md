# Proposal: POC — VelesDB 推测性预取 (Speculative Prefetch) 研究

> track: poc
> status: proposal
> 日期: 2026-08-09
> Trunk SHA: 3e98f3e
> 关联: BEH-024 (WILLNEED), BEH-027 (WILLNEED_BG), DEC-070, DEC-074

## 1. 研究背景

### 1.1 当前系统瓶颈

DiskHNSW 的 I/O 路径为：`bg_thread sched_yield → fadvise(WILLNEED) → kernel readahead → pread`。

Trunk profiling (SHA=4697c0d, 256MB 1T EF=100) 显示：
- **内核占 43.7% CPU**（fadvise + readahead + pread 系统调用）
- **bg_thread sched_yield 自旋占 ~18.4%**（提供零延迟 fadvise 提交）
- 每 query: pread=50.8 次, fadvise=42.4 次, sched_yield=2,116 次
- 已尝试的优化（futex/io_uring/hybrid pause+yield）全部在严格 A/B 下无收益

**核心限制**：bg_thread 只能在当前层搜索完成后才能提交下一层的 WILLNEED。
从 layer N 完成 到 layer N+1 需要 pread 之间存在 **等待窗口**——kernel readahead
尚未完成时，pread 命中 cold page，触发同步磁盘 I/O。

### 1.2 VelesDB 的做法

VelesDB（Rust 实现的端侧 AI 记忆引擎）在 HNSW 搜索中采用了 **software prefetching**
策略，与我们的 WILLNEED (kernel-level fadvise) 不同，它同时使用了：

1. **CPU cache prefetch**（`_mm_prefetch` / ARM `PRFM` 指令）
   - 在遍历 candidate list 时，提前 N 个位置 prefetch 下一个 candidate 的向量到 L1/L2/L3
   - `calculate_prefetch_distance(dimension)` 根据向量维度动态计算 prefetch 距离
   - 在 batch distance computation 循环中 `prefetch_vector(candidates[i + distance])`

2. **Contiguous memory layout** + BFS reorder
   - 向量连续存储（cache-friendly），BFS 重排序使图中相邻节点在内存中也相邻
   - 减少 cache miss，使 CPU prefetch 更有效

3. **Multi-level prefetch strategy**
   - L1 (PRFM PLDL1KEEP): 即将访问的向量
   - L2 (PRFM PLDL2KEEP): 1-2 步后访问的向量
   - L3 (PRFM PLDL3KEEP): 3-4 步后访问的向量

### 1.3 相关论文

| 论文 | 关键发现 |
|------|---------|
| arXiv:2505.07621 "Bang for the Buck" (DaMoN'25) | CPU 微架构对向量搜索性能影响巨大；HNSW 在不同 CPU 上 QPS 差 3x；cache 层级是关键 |
| arXiv:2508.03016 "KBest" (KDD'26) | Kunpeng 920 上的硬件感知优化：SIMD + data prefetch + early termination，2x QPS 提升 |
| arXiv:2603.01779 "Disk-Resident Graph ANN" (2026) | 系统性评估磁盘 ANN：storage / layout / cache / execution / update 五维度；layout I/O 利用率 ≤15% |
| arXiv:2602.21514 "OctopusANN" (PVLDB'26) | I/O-first 框架：memory-resident navigation + dynamic width 提供最大 standalone gain；比 DiskANN +87.5~149.5% |

## 2. 研究问题

**核心问题**：能否在 HNSW 图遍历的 **search loop 内部** 做 speculative prefetch，
在搜索层 N 时就为层 N+1 的最可能候选节点提前发起 pread/fadvise，
从而在层切换时消除等待窗口？

### 子问题

1. **CPU cache prefetch 对 DiskHNSW 有效吗？**
   - DiskHNSW 的瓶颈在 disk I/O（pread），不在 CPU cache miss
   - 但 FineRerank 阶段的 PQ ADC 计算是 CPU-bound 的
   - VelesDB 的 prefetch 策略针对内存中的向量，不针对磁盘 I/O

2. **推测性 I/O 预取（speculative fadvise/pread）可行吗？**
   - 在搜索层 N 的 candidate list 中，基于 PQ 粗筛距离 **预测** 层 N+1 可能访问的节点
   - 提前对这些节点发起 fadvise(WILLNEED)
   - 风险：wasted prefetch（预测错误），wasted memory bandwidth

3. **VelesDB 的 contiguous layout + BFS reorder 对我们有启发吗？**
   - 我们已有 BFS reorder（block layout）
   - 但 vecblocks 是按 64K 块组织的，不是 per-vector contiguous
   - FineRerank 在 page 粒度工作，需要整页读入

## 3. POC 方向

### R0: Baseline Profiling
- 在 Trunk SHA=3e98f3e 上做 perf profiling
- 量化 FineRerank PQ ADC 计算的 CPU cache miss rate
- 量化层切换时的 pread 延迟分布
- 判断瓶颈到底在 CPU cache 还是 disk I/O

### R1: CPU Prefetch for PQ ADC (VelesDB-style)
- 在 FineRerank 的 PQ ADC 循环中插入 `_mm_prefetch`
- prefetch 距离 = `calculate_prefetch_distance(dimension)`
- 预期：如果 PQ ADC 有 cache miss 瓶颈，则 +5~15% QPS
- 风险：如果 PQ ADC 已经在 L1 中（数据量小），无收益

### R2: Speculative WILLNEED for Next-Layer
- 在层 N 搜索过程中，对 candidate list 按 PQ 粗筛距离排序
- 对 top-K 候选的邻居提前发起 WILLNEED（不等层 N 完成）
- 预期：减少层切换时的 pread 等待窗口
- 风险：wasted prefetch 增加 fadvise 开销

### R3: Batch Prefetch Pipeline
- 将 candidate list 分批，batch[0] 做距离计算时，batch[1] 的向量被 prefetch
- 类似 VelesDB 的 `batch_dot_with_prefetch(candidates, query, prefetch_distance)`
- 预期：隐藏 FineRerank 阶段的 memory latency

## 4. 与已拒绝 POC 的区别

| 已拒绝 POC | 失败原因 | 本 POC 的不同 |
|-----------|---------|--------------|
| bg-thread-futex (R1 io_uring) | 异步队列延迟 + SQ 非线程安全 | R1 目标是 CPU cache，不是 disk I/O |
| bg-thread-futex (R0 futex) | wake 延迟导致 fadvise 滞后 | R2 在搜索线程内做，不经 bg_thread |
| bg-thread-futex (hybrid pause) | 严格 A/B 无收益 | R1/R3 目标是不同瓶颈（CPU cache vs yield） |

## 5. 实验计划

### 测试配置
- 金标配置 A (M=16, EF=100, 256MB 1T) — SLA 基线
- 金标配置 C (M=24, EF=60, 512MB 16T) — 高吞吐场景
- 严格 A/B 对比（同 session 交替跑新旧 binary）
- 3 轮 × 2 配置

### 验收标准
- R1: agg QPS Δ ≥ +3%（CPU cache miss 如是瓶颈）
- R2: pread wait time 减少 ≥ 20%（strace + perf 测量）
- R3: FineRerank latency 减少 ≥ 10%
- 回归：recall 下降 < 0.3pp

## 6. 参考资料

### VelesDB 源码
- `crates/velesdb-core/benches/prefetch_tuning_benchmark.rs` — prefetch 距离调优基准
- `crates/velesdb-core/src/perf_optimizations.rs` — ContiguousVectors + prefetch API
- `crates/velesdb-core/src/simd_neon_prefetch.rs` — ARM64 PRFM 指令封装
- `crates/velesdb-core/src/index/hnsw/native/` — HNSW native 实现

### 论文
- [arXiv:2505.07621] "Bang for the Buck: Vector Search on Cloud CPUs" (DaMoN'25)
- [arXiv:2508.03016] "KBest: Efficient Vector Search on Kunpeng CPU" (KDD'26)
- [arXiv:2603.01779] "Disk-Resident Graph ANN Search: An Experimental Evaluation" (2026)
- [arXiv:2602.21514] "I/O Optimizations for Graph-Based Disk-Resident ANN" (PVLDB'26)

### VelesDB 文档
- https://velesdb.com/en/docs/
- https://deepwiki.com/cyberlife-coder/VelesDB/3.2-search-pipeline-and-distance-metrics
