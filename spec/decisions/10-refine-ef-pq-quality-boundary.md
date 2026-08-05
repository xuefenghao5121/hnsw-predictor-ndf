# Decisions - refine-ef-tuning + pq-quality 边界确认 (DEC-072)

> 条款索引: `DEC-072`

## D-072: DEEP10M PQ/REFINE_EF 优化边界确认 {#DEC-072}
<!-- ndf: kind=decision date=2026-08-04 source=observed -->
<!-- ndf: rejects=refine-ef-tuning,pq-quality depends-on=DEC-070,CON-SLA-014,CHR-006 -->

**Context.** 在 WILLNEED（DEC-070）合入 Trunk 后，对 DEEP10M 2GB cgroup（CON-SLA-014）
做了 REFINE_EF × PQ M 联合扫描，确认 Recall≥95% 约束下的优化边界。

### REFINE_EF 扫描（M=32, WILLNEED=1）

| EF | Recall | QPS | SLA |
|----|--------|-----|-----|
| 300 | 95.05% | 567 | ✅ |
| 250 | 94.85% | 634 | ❌ |
| 200 | 94.25% | 751 | ❌ |

### PQ M 扫描（EF=300, WILLNEED=1）

| M | Recall | QPS | SLA |
|---|--------|-----|-----|
| 32 | 95.05% | 567 | ✅ |
| 24 | 94.05% | 670 | ❌ |

### OPQ M=24 实验

OPQ 旋转矩阵与 HNSW 图结构不兼容（图邻居基于原始 L2 空间），Recall=1.25%，不可行。

### PQ × EF 联合扫描

| M | EF | Recall | QPS | SLA |
|---|-----|--------|-----|-----|
| 24 | 250 | 93.45% | 756 | ❌ |
| 24 | 200 | 92.40% | 906 | ❌ |

**Decision.** Recall≥95% 约束下（[[CHR-006]]），EF=300+M=32 是 DEEP10M 唯一达标组合。
关闭 refine-ef-tuning 和 pq-quality 两个 topic。

提升 DEEP10M QPS 的唯一路径是放宽 SLA（另开 process 提案），或在 100M 规模重新评估。

**Consequences.**
- refine-ef-tuning: TOPIC=rejected, POC ndf 归档
- pq-quality: TOPIC=rejected, POC ndf 归档
- Trunk 无需改动
- M=32+EF=300 确认为 DEEP10M 生产默认（已在 README/detailed-design）

**Trunk impact.** 无。所有实验仅 POC 目录。
