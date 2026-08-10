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
