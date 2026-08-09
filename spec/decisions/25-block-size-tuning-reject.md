# DEC-089: Block Size 调优负结果 — M=16 下无收益 {#DEC-089}

> date: 2026-08-09
> affects: DEC-087, DEC-088
> Rejects: block-size-tuning
<!-- ndf: depends-on=DEC-087,DEC-088 -->

## Context

pipeline-param-retuning (DEC-087) R4' 在 M=24 上发现 32K vs 64K block size +52.5% QPS，
但延期未在 M=16 上深入验证。block-size-tuning POC 独立验证 M=16 EF=65（DEC-087 最优配置）
下 block size 的影响。

## 实验

M=16 EF=65, 256MB cgroup, sustained (N=1000, R=15, seed=42), BS = {16K, 32K, 48K, 64K, 128K}。

### Block Size 扫描 (1T BASE)

| BS | Agg QPS | Steady QPS | Recall |
|----|---------|-----------|--------|
| 16K | 1,609 | 1,713 | 95.52% |
| 32K | 1,440 | 1,694 | 95.52% |
| 48K | 1,487 | 1,720 | 95.52% |
| 64K | 1,480 | 1,653 | 95.52% |
| 128K | 1,543 | 1,698 | 95.52% |

agg 极差 ±5.9%，steady 极差 ±2.0% — 全在噪声内。

### 32K 多线程

| 配置 | Agg QPS | Steady QPS | Recall |
|------|---------|-----------|--------|
| 1T BASE | 1,440 | 1,694 | 95.52% |
| 4T BASE | 3,040 | 4,363 | 95.52% |
| 16T BASE | 2,924 | 4,464 | 95.52% |
| 1T ADAPTIVE | 1,595 | 1,908 | 95.17% |
| 16T ADAPTIVE | 3,734 | 5,885 | 95.17% |

## 根因分析

Block size 仅在 page cache 覆盖率 < 5% 时有意义：

| M_graph | page_cache | 覆盖率 | BS 32K 收益 |
|---------|-----------|--------|------------|
| 24 | 24MB | 4.8% | +52.5% ✅ |
| 16 | 27MB | 5.4% | -2.7%（噪声）❌ |

M=16 CSR 最小（47MB），留给 page cache 最多（27MB），覆盖率刚好跨过 5% 门槛。
block size 缩小减少的 I/O 浪费在 page cache 充足时被吸收。

## 与 DEC-088 框架的一致性

DEC-088 决策树步骤 5：「仅当 page_cache 覆盖率 < 5% 时扫描 block size」。
本 POC 验证了 > 5% 时无收益的预测，框架与实验完全吻合。

## 结论

- **M=16 下 block size 无收益**，保持 Trunk 默认 64K
- **不 promote 任何条款**
- 负结果闭环：TOPIC=rejected，binder archive
- 框架 5% 门槛得到实验验证

> source: poc/block-size-tuning/ndf/evidence/r0-block-size-scan-20260809.md
> Rejects: block-size-tuning
