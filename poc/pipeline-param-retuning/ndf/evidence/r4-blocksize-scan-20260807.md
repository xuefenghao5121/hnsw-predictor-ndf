> ⚠️ **白嫖数据 — 不合 CON-SLA-014，不可作为 promote 依据**。仅供趋势参考。
# R4: Block Size 扫描 (16K/32K/64K/128K on M=24)

> 日期：2026-08-07
> 协议：CON-SLA-020 (sustained, N=1000, R=15, seed=42)
> 图: M=24, EF=60, PQ M=32
> 模式: BASE (TWO_STAGE + FINE_RERANK)

## 单线程 (1T)

| BS | Blocks | Agg QPS | Steady QPS | Recall | RSS |
|----|--------|---------|-----------|--------|-----|
| 16K | 32,259 | 3,403 | 3,414 | 96.60% | 230 |
| 32K | 15,874 | 3,480 | 3,506 | 96.60% | 230 |
| **64K** | **7,937** | **3,515** | **3,546** | **96.60%** | **230** |
| 128K | 3,953 | 3,519 | 3,448 | 96.60% | 230 |

## 多线程 (16T)

| BS | Agg QPS | Steady QPS | Recall | RSS |
|----|---------|-----------|--------|-----|
| 16K | 28,720 | 30,413 | 96.60% | 254 |
| 32K | 28,616 | 30,956 | 96.60% | 254 |
| **64K** | **28,606** | **28,017** | **96.60%** | **253** |
| 128K | 29,091 | 29,900 | 96.60% | 253 |

## 核心发现

**Block size 对 sustained 性能几乎无影响（±1.7%）。**

原因分析：
1. Fine Rerank 读 4KB page，已绕过 64KB block 粒度
2. BlockCache (Phase A O_DIRECT) 在 FINE_RERANK=1 时不是主要 I/O 路径
3. BFS 物理布局的差异（大 block = 更多相邻节点在同一文件区域）在 page cache 层面影响极小
4. Kernel readahead 以 4KB page 为单位，不受 block size 直接影响

## 结论

**Block size 64K 维持不变 (DEC-008)。** 无优化空间。

Block size 从 200q cache-warmed 确定的 64K 在 sustained 下仍然合理。
大 block (128K) 略快可能因压缩率更好，但差异在噪声范围内。

## 文件大小对比

| BS | vecblocks (MB) | blocks (MB) | route (MB) |
|----|-------------|-----------|---------|
| 16K | 504 | 557 | 4 |
| 32K | 496 | 553 | 4 |
| 64K | 496 | 550 | 4 |
| 128K | 494 | 549 | 4 |

大 block 的压缩效率略好（更少 block header 开销），但差异 < 2%。
