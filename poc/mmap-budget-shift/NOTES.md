# Notes: mmap Budget Shift POC

> 创建: 2026-08-09
> Trunk SHA: 434c6f5 (审计修正)
> Status: R0 REJECTED

## R0 结果 (2026-08-10)

### 测试配置
- 协议: CON-SLA-020 sustained, CON-SLA-019 禁预热
- 配置: Config C (DEC-087: M=24, EF=60)
- cgroup: 256MB, 1T, 15轮 × 1000q, seed=42

### A/B 对比

| | A (vector PQ) | B (mmap PQ) | 变化 |
|--|---------------|-------------|------|
| agg QPS | **1,407.9** | **348.2** | **-75.3%** |
| steady QPS | **1,656.0** | **328.1** | **-80.2%** |
| recall | 96.60% | 96.60% | 0 (正确) |
| RSS after init | 109 MB | 79 MB | -30 MB (mmap 确实释放 anon) |
| RSS (search) | 232 MB | 230 MB | ~相同 |

### 金标验证
- A 基线: agg 1,407.9 vs 金标 1,450 (±2.8%, 在 ±2CV 内 ✅)
- Recall: 96.60% = 金标 96.60% ✅

### 根因分析

mmap PQ codes 导致 **4x QPS 退化**：

1. **Page cache 争夺**: PQ codes (30MB file-backed) 与 vecblocks 在 page cache 中争夺空间
   - PQ codes 随机访问，每 query 访问 ~21 个节点 × 32B = 672B
   - vecblocks 也随机访问，但每 block 64KB
   - kernel LRU 无法区分：PQ code 页面是 hot 但小量，vecblocks 页面是 warm 但大量
   - 结果：PQ code 页面被频繁 evict/reload，或 vecblocks 页面被 PQ 挤占

2. **mmap page fault 开销**: 每次首次访问 PQ code 页面触发 minor fault
   - 30MB / 4KB page = 7,680 页
   - 随机访问模式下，page fault 分散在搜索过程中，无法批量预热

3. **RSS 对比证实**: init 后 RSS 从 109MB 降到 79MB (-30MB)，说明 mmap 确实释放了 anon 预算
   - 但 search 阶段 RSS 都是 ~230MB，说明 mmap 的 30MB 在搜索时被 page-in
   - net 效果：anon 减 30MB，file 增 30MB，但 file 中的 PQ codes 争夺 vecblocks cache

### 结论

**R0 REJECTED**: mmap PQ codes 导致 75% QPS 退化。

核心假设错误：mmap 释放的 anon 预算确实转化为 file 预算，但 PQ codes 自身作为 file-backed 数据与 vecblocks 争夺 page cache，导致净效果为负。

**与 R5c 一致**: R5c mincore 诊断结论是"页缓存在 Pareto 前沿"——当前 anon/file 分配已是最优。mmap 改变记账方式但引入 cache 争夺，比 Pareto 更差。

### 不继续 R1

R1 原计划 mmap CSR (57MB)，预期退化更大（CSR 访问频率高于 PQ codes）。不继续。

### 关键教训

1. **mmap 不是免费午餐**: 释放 anon 预算的代价是 file-backed 数据争夺 page cache
2. **Pareto 前沿不可突破**: R5c 的结论仍然成立，anon/file 分配已是最优
3. **page cache LRU 不适合混合工作负载**: PQ codes (hot, small, random) + vecblocks (warm, large, random) 在同一 LRU 中无法最优管理
