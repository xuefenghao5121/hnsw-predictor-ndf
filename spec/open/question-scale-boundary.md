# Q-001: 图遍历的规模上限 {#Q-001}
<!-- ndf: kind=open blocks=DEC-026,ARCH-004,P3 source=deduced date=2026-07-29 -->

## 问题

DiskHNSW 的 HNSW 图遍历产生串行 I/O 依赖链：每步扩展依赖前一步读到的邻居。
HELMSMAN 论文验证了这种模式在 100M+ 规模导致无法满足在线 SLA。

**DiskHNSW 在什么规模下图遍历的 I/O 串行化成为不可接受的瓶颈？**

## 子问题

1. 10M 规模：vecblocks ~5GB，每 query 约 100-200 次 4KB 页读。page cache 部分覆盖 +
   io_uring batched 提交，I/O 占比预计多少？

2. 100M 规模：vecblocks ~50GB，page cache 完全失效。每 query 约 100-200 次真实磁盘 I/O。
   在 NVMe SSD ~50μs/页 下，I/O 时间 = 5-10ms，是否超过 SLA？

3. 是否存在"混合范式"（图用于上层导航，聚类用于 L0 向量存储）的可能性？

## 相关决策

- [[DEC-026]] — P2 保留图方法，P3 重新评估
- [[DEC-006]] — BFS 重排优化空间局部性

## 决议条件

P2（10M 规模）完成后，根据实测 I/O 占比决定：
- I/O 占比 <50% → 图方法在 10M 可行，P3 可选
- I/O 占比 50-80% → P3 需考虑 I/O 优化（SPDK 等）
- I/O 占比 >80% → P3 需认真考虑聚类范式

## 状态

开放。预计 P2 完成后（2026 Q3）有初步答案。
