# R0: Block Size Scan — M=16 EF=65 256MB Sustained

> date: 2026-08-08/09
> topic: block-size-tuning
> protocol: CON-SLA-014 + CON-SLA-019 + CON-SLA-020 (sustained, N=1000 R=15 seed=42)

## 配置

```
M_graph=16, EF=65, 256MB cgroup
TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
FLAT_VEC_MB=64 CACHE_MB=64 ADAPTIVE_EF=0
```

## Block Size 扫描 (1T BASE)

| BS | Agg QPS | Steady QPS | Recall |
|----|---------|-----------|--------|
| 16K | 1,609 | 1,713 | 95.52% |
| 32K | 1,440 | 1,694 | 95.52% |
| 48K | 1,487 | 1,720 | 95.52% |
| 64K | 1,480 | 1,653 | 95.52% |
| 128K | 1,543 | 1,698 | 95.52% |

agg 极差 ±5.9%，steady 极差 ±2.0% — 全在噪声内。

## 32K 多线程 + ADAPTIVE

| 配置 | Agg QPS | Steady QPS | Recall |
|------|---------|-----------|--------|
| 1T BASE | 1,440 | 1,694 | 95.52% |
| 4T BASE | 3,040 | 4,363 | 95.52% |
| 16T BASE | 2,924 | 4,464 | 95.52% |
| 1T ADAPTIVE | 1,595 | 1,908 | 95.17% |
| 16T ADAPTIVE | 3,734 | 5,885 | 95.17% |

16T BASE agg (2,924) 低于 4T agg (3,040)，多线程扩展有退化（与 CON-SLA-020 一致）。

## 框架对照 (DEC-088)

| 预测 | 实际 | 吻合 |
|------|------|------|
| 覆盖率 5.4% > 5% → 差异 < ±10% | agg ±5.9%, steady ±2.0% | ✅ |

## 结论

**M=16 下 block size 无收益。** 与 pipeline-param-retuning R4' 的 M=24 结果（32K +52.5%, 覆盖率 4.8% < 5%）形成对照。

Block size 仅在 page cache 覆盖率 < 5% 时有意义。M=16 CSR 最小 → page cache 最大 → block size 无影响。

> source: poc/block-size-tuning/results/m16_ef65_bs*.log
