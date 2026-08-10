# Notes: mmap Budget Shift POC

> 创建: 2026-08-09
> Trunk SHA: 434c6f5
> Status: R0 REJECTED (re-run with golden script confirmed)

## R0 结果 (2026-08-10, scripts/run_sustained.sh 金标)

### 测试配置
- 脚本: `scripts/run_sustained.sh`（CON-SLA-020 金标载体，source cgroup_utils.sh）
- 协议: CON-SLA-020 sustained, CON-SLA-019 禁预热, CON-SLA-014 严格 cgroup
- 配置: Config C (DEC-087: M=24, EF=60)
- cgroup: 256MB, 1T, 15轮 × 1000q, seed=42

### A/B 对比

| | A (vector PQ) | B (mmap PQ) | Delta |
|--|:---:|:---:|:---:|
| agg QPS | **1,431.6** | **277.0** | **-80.6%** |
| steady QPS | **1,662.7** | **267.4** | **-83.9%** |
| recall | 96.60% | 96.60% | 0 (正确) |
| RSS after init | 109 MB | 79 MB | -30 MB (mmap 释放 anon) |
| RSS (search) | 232 MB | 230 MB | ~相同 |
| Ramp-up | 167.5% | 5.0% | mmap 无热身效果 |

### 金标验证
- A 基线: agg 1,431.6 vs 金标 1,450 (−1.3%, 在 ±2CV 内 ✅)
- Recall: 96.60% = 金标 96.60% ✅

### 根因分析

1. **Page cache 争夺**: PQ codes (30MB file-backed) 与 vecblocks 在 page cache 中争夺
   - PQ codes 每 query 访问 ~21 节点 × 32B = 672B（hot, 小量, 随机）
   - vecblocks 每 block 64KB（warm, 大量, 随机）
   - kernel LRU 无法区分两种工作负载 → thrashing

2. **Ramp-up 仅 5%**: A 的 round 1/round 15 = 621/1663 = 37%（冷启动正常）
   B 的 round 1/round 15 = 255/267 = 95%（看起来"稳定"，但绝对值极低）
   → mmap PQ codes 从始至终都慢，page fault + cache 争夺贯穿全部 15 轮

3. **RSS 证实 mmap 确实工作**: init 109→79MB (−30MB)，但 search 阶段 page-in 后 RSS ~相同

### 结论

**R0 REJECTED**: mmap PQ codes 导致 80.6% QPS 退化。核心假设错误——mmap 释放 anon
预算的代价是 PQ codes 自身作为 file-backed 数据争夺 page cache。与 R5c 结论一致：
页缓存在 Pareto 前沿。不继续 R1。

## R1 结果 (2026-08-10, scripts/run_sustained.sh 金标)

### 测试配置
- 脚本: scripts/run_sustained.sh
- 配置: Config C (M=24 EF=60), 256MB 1T, 15轮×1000q, seed=42

### A/B 对比

| | A (vector CSR) | B (mmap CSR) | Delta |
|--|:---:|:---:|:---:|
| agg QPS | 1,427.7 | 480.6 | **-66.3%** |
| steady QPS | 1,638.3 | 495.5 | **-69.8%** |
| recall | 96.60% | 96.60% | 0 ✅ |

A vs 金标 1,450: -1.5% (±2CV 内 ✅)

### 与 R0 对比

| 数据结构 | 大小 | 退化幅度 | 根因 |
|----------|------|---------|------|
| PQ codes | 30MB | -80.6% | 纯随机, 无局部性 |
| CSR | 57MB | -66.3% | BFS 局部性有帮忙, 但 57MB 争夺面更大 |

CSR 的 BFS 局部性确实减轻了 page cache 争夺（退化幅度 -66% vs -80%），
但 57MB file-backed 面积太大，净效果仍然严重负。

### 最终结论

R0 (PQ codes) + R1 (CSR) 均 REJECTED。mmap anon→file 预算转移方向证伪。
与 R5c Pareto 前沿结论一致。
