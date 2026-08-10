# Notes: SSD Parallelism I/O Optimization

> 创建: 2026-08-10
> Trunk SHA: 434c6f5
> Status: exploring (R0 pending)

## 论文摘要

**Turbocharging Vector Databases using Modern SSDs** (VLDB 2025, Shim et al.)

三大技术:
1. io_uring 并行邻居检索 + CQE peeking（按完成顺序计算距离）
2. 空间感知插入重排（动态插入提升 cache 复用）
3. 局部性保持共置（预聚类到相同 page）

结果: 最高 11.1× QPS, 3.23× cache hit, 98.4% build time reduction
基础: pgvector 0.8.0 + PostgreSQL 17

## 与 DiskHNSW 的差异

| 维度 | pgvector (论文) | DiskHNSW (我们) |
|------|-----------------|-----------------|
| I/O 路径 | PostgreSQL buffer cache -> read() | pread() + fadvise(WILLNEED) |
| 并行 I/O | 无（阻塞 read） | WILLNEED_BG 后台线程（无锁 SPSC） |
| 完成顺序 | 批量屏障 | pread 固定顺序 |
| io_uring | 无 | 有（FINE_PREAD=0），多线程退化 pread |

## 已 rejected 方向的教训

- DEC-071 (io-pipelining): pipe_ring_ 预取与 WILLNEED 重叠 -> 无收益
- DEC-094 (mmap-budget-shift): page cache thrashing -> -66~80% QPS
- data-layout (BFS 重排): ceiling ~4% QPS

## R0 待实现

方向 A: io_uring CQE peeking 替代 pread
方向 B: k-means 聚类重排 vecblocks

## R0 结果 (2026-08-10, scripts/run_sustained.sh 金标)

### 方向 A: io_uring CQE peeking 替代 pread

配置: Config C (M=24 EF=60), 256MB 1T, 15轮×1000q, seed=42
A = WILLNEED_BG + pread (FINE_PREAD=1, 现有路径)
B = WILLNEED_BG + io_uring CQE peeking (FINE_PREAD=0, patch: 完成顺序处理)

| | A (pread) | B (CQE peeking) | Delta |
|--|:---:|:---:|:---:|
| agg QPS | 1,414.3 | 1,463.1 | **+3.5%** |
| steady QPS | 1,616.2 | 1,699.0 | **+5.1%** |
| recall | 96.60% | 96.60% | 0 ✅ |
| Round 1 | 604.1 | 631.4 | +4.5% |
| Round 15 | 1,616.2 | 1,699.0 | +5.1% |

A vs 金标 1,450: -2.5% (在 ±2CV 边缘 ✅)
B vs 金标 1,450: +0.9% (在金标范围内 ✅)

### 分析

CQE peeking 的收益来自:
1. **消除批量屏障**: 不等全部 I/O 完成，先到先算，CPU 不空闲
2. **SSD 通道不对称**: NVMe 多通道完成时间不一致，peeking 利用先完成的 I/O
3. **与 WILLNEED 协同**: WILLNEED 预热 page cache，io_uring 读取已预热页面更快完成

与 DEC-071 (io-pipelining) 的区别验证:
- DEC-071: pipe_ring_ 预取与 WILLNEED 重叠 -> 无收益 (两者同一时机)
- 本 POC: io_uring 替代 pread，CQE 完成顺序处理 -> +3.5% 收益
- 根因: 不是预取问题，而是完成顺序问题 (pread 固定顺序 vs CQE 完成顺序)

### 结论

方向 A 正向 (+3.5% agg / +5.1% steady)，值得继续探索。
方向 B (k-means 聚类重排) 待定。
