# Proposal: Data Layout Optimization for LLC Miss Reduction

> status: exploring
> track: poc
> created: 2026-08-09
> baseline_trunk_sha: 3e98f3e
> baseline_status: current

## 背景

R0 gold standard profiling（256MB 1T cgroup, 15轮×1000q）揭示真正瓶颈：

| 瓶颈 | 占比 | 数据 |
|------|------|------|
| **LLC miss → DRAM latency** | **~74%** | 5,087 miss/query, 58.1% miss rate |
| CPU compute | ~24% | IPC=2.37, L1 miss 2.2% |
| Disk I/O | ~3% | Major fault 0.50/query |

内存数据结构总量 ~284MB，远超 L3 cache (~30MB)，导致 58.1% LLC miss rate。

### 瓶颈数据结构

| 数据结构 | 内存 | 访问模式 | 是否受益于布局优化 |
|----------|------|----------|-------------------|
| **CSR adjacency (edges)** | 91.6 MB | 随机（按 node_id 查 offsets） | ✅ BFS reorder 已做，可改进 |
| **PQ codes** | 30.5 MB | 随机（按 node_id 查 32B code） | ✅ BFS reorder 已做，可改进 |
| **PQ dist table** | 32 KB | 固定（per-query 预计算） | 在 L2 中，无需优化 |
| **CSR offsets** | 3.8 MB | 随机（按 node_id） | ✅ 与 BFS reorder 联动 |
| Block cache | 64 MB | LRU | 不在本次范围 |
| flat_vec_cache | 64 MB | LRU | 不在本次范围 |

### 关键观察

1. **PQ codes**: 每节点 32B = 半个 cache line。BFS reorder 后，graph 邻居 node_id 接近
   → 2 个邻居可能共享同一 cache line → 减少 LLC miss
2. **CSR edges**: BFS reorder 后相邻节点的 edge list 位置接近
   → offsets[n] 和 offsets[n+1] 可能在同一 cache line
3. **PQ dist table**: 32KB，超过 L1 (32KB) 但在 L2 (1MB) 中
   → pqDistance() 的 table lookup 是 L2 hit，不是瓶颈

## 论文研究

### 1. Graph Reordering for Cache-Efficient Near Neighbor Search (Coleman et al., NeurIPS 2022)

- **arxiv**: 2104.03221
- **核心思想**: graph reordering — 将常一起访问的节点放在连续内存位置
- **效果**: HNSW 上 10-40% 查询加速
- **方法**: 6 种 reordering 算法对比，objective-based 方法最优
  - SlashBurn: 迭代移除 hub 节点
  - GOrder: 最大化邻居窗口内重叠
  - Rabbit-Order: 基于社区检测
  - **Metric Forest**: 基于 BFS + cache miss 目标函数
- **关键发现**: reordering 时间远小于 index 构建时间
- **与我们**: 我们已有 BFS reorder，但 BFS ≠ 最优。论文的 objective-based 方法可以考虑实际搜索路径

### 2. CS-PQ: Cache-Friendly SIMD Product Quantization (Huang et al., VLDB 2025)

- **arxiv**: 2605.25521
- **华为合作论文**（作者含华为员工）
- **核心思想**: 重构 PQ 计算流水线，将 LUT 保留在寄存器中
- **效果**: PQ 构建加速 10.7x（注意：这是构建阶段，非查询阶段）
- **与我们**: 我们的 PQ 是查询阶段 ADC 距离计算。dist table 在 L2，PQ code 在 DRAM
  - 可以借鉴 vector-oriented SIMD 思路优化 pqDistance()
  - 但我们的 PQ ADC 瓶颈不是计算而是 PQ codes 的随机访问

### 3. FAISS FastScan (André et al., VLDB 2015)

- **核心思想**: 4-bit PQ + SIMD shuffle（LUT 放在 SIMD 寄存器中）
- **效果**: 避免 memory lookup，全程寄存器计算
- **与我们**: 我们的 PQ ADC 用 float LUT (32KB)，在 L2 中
  - FastScan 的 4-bit PQ 精度损失太大（需要 rerank）
  - 但 block-level code packing 思路可借鉴

### 4. d-HNSW (Shine, arxiv 2507.17647)

- RDMA-friendly data layout for disaggregated memory
- 与我们的 disk-based 场景不同，但 layout 思路可参考

## R0 Plan: 量化 BFS reorder 的效果天花板

**目标**: 测量当前 BFS reorder 的 cache locality，估算改进空间

### 实验设计

1. **对比 BFS vs random order vs Hub-based order**
   - 已有: BFS reorder（当前 Trunk）
   - 新增: 随机排列、原始顺序
   - 测量: LLC miss rate, QPS, recall

2. **测量 PQ code access locality**
   - 在 searchLayer0 中记录访问的 node_id 序列
   - 分析: 连续访问的 node_id 差值分布
   - 估算: 理论 cache line sharing 比例

3. **模拟理想布局的 LLC miss 下界**
   - 如果所有 graph 邻居都在同一 cache line → LLC miss 减少？
   - 用 Cachegrind 或 perf c2c 分析

### 预期结论

- 如果 BFS 已接近最优 → LLC miss 无法通过 reorder 减少 → POC rejected
- 如果 BFS 与最优差距大 → R1: 实现更优 reorder 算法

## R1 候选方向（取决于 R0 结果）

### R1-A: 搜索路径感知 reordering

基于 Coleman 论文的 objective-based 方法：
- 采集 1000 次搜索的实际 node 访问序列
- 构建 access frequency matrix
- 用 Metric Forest 算法重新排列 node_id

### R1-B: PQ code 布局优化

当前: `pq_codes_[node_id * M]` — 按 node_id 排列
改进方案:
- **SoA (Struct of Arrays)**: 按 sub-quantizer 分离存储
  - `pq_codes_subm[node_id]` for each m ∈ [0, M)
  - 使得同一次 pqDistance 的 M 次查表分散到 M 个独立数组
  - 但这可能增加 cache line 使用量
- **Blocked layout**: 将频繁一起访问的 node 的 PQ code 打包到同一 cache line

### R1-C: CSR edge list 压缩

当前: CSR edges 数组存储原始 node_id (4 bytes/edge)
改进:
- 使用 delta encoding + varint
- 减少 edge array 大小 → 减少 cache footprint
- 但增加解码开销

## 协议

- 配置: 金标 A (256MB 1T EF=100, 15轮×1000q)
- 对比: BFS vs random vs 其他 reorder
- 指标: QPS, recall, LLC miss rate, L1 miss rate
- 约束: recall ≥ 95%, 不修改 Trunk src/

## 关联条款

- CON-GOLDEN-001 (golden config)
- META-006 (golden rerun rule)
- DEC-070, DEC-074 (architecture decisions)
- BEH-024 (WILLNEED), BEH-027 (WILLNEED_BG)
