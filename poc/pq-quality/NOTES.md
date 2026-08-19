# POC: PQ Quality

> status: rejected
> close: reject | 2026-08-04 | [[DEC-072]]（M=32 为 SLA 达标唯一选择）
> 提案: `spec/open/proposal-pq-quality.md`（Implemented / Rejected）
> 基线: DEEP10M 2GB cgroup, Buffered 1T, EF=300, flat_vec=128MB

## R0-R2 结果 (2026-08-03, CON-SLA-014, 2GB cgroup, 200q, 1T)

| PQ | dsub | codes 大小 | Recall | QPS | RSS | majfault | vs R0 |
|----|------|-----------|--------|-----|-----|----------|-------|
| M=32 (基线) | 3 | 305MB | **95.05%** | 530 | 1257 | 70145 | 基线 |
| M=48 | 2 | 458MB | **95.30%** | 517 | 1410 | 73809 | -2% QPS, +0.25pp recall |
| M=24 | 4 | 229MB | **94.05%** | **707** | 1183 | 70108 | **+33% QPS**, -1pp recall |

### 关键发现

1. **M=24 (dsub=4) 是最佳选择**: QPS +33%, Recall 仅降 1pp (95.05->94.05%)
   - PQ codes 更小 (229MB vs 305MB) -> RSS 降 74MB -> 更多 page cache 预算
   - dsub=4 子空间更大，PQ 粗筛质量足够好
2. **M=48 (dsub=2) 无收益**: Recall 仅 +0.25pp, QPS 反降 2%
   - PQ codes 更大 (458MB) -> RSS 涨 153MB -> 挤占 page cache
   - dsub=2 子空间太小，PQ 质量提升有限
3. **M=24 + REFINE_EF=200 联合潜力大**:
   - M=24 recall=94.05% (EF=300), 降 EF=200 可能仍 >93%
   - QPS = 707 × (865/685) ≈ 893 QPS（联合估算）

### 与 refine-ef-tuning 联合分析

| 配置 | Recall | QPS | 说明 |
|------|--------|-----|------|
| M=32, EF=300 | 95.05% | 530 | 当前基线 |
| M=24, EF=300 | 94.05% | 707 | +33% |
| M=32, EF=200 | 94.25% | 865 | +63% (refine-ef POC) |
| M=24, EF=200 | ~93.5%? | ~1000? | 联合（待验证） |

## 进度

- [x] R0: M=32, dsub=3 (基线)
- [x] R1: M=48, dsub=2
- [x] R2: M=24, dsub=4
- [ ] R3: M=24 + EF=200 联合验证
- [ ] 决策

## R4: OPQ M=24 实验 (2026-08-04)

### 尝试
- 训练 OPQ 旋转矩阵 + PQ M=24 编码
- 用旋转后的 query 跑 benchmark

### 结果
- **Recall 1.25%** — 完全失败
- QPS 548（正常范围），但搜索结果错误

### 根因
**OPQ 旋转空间与 HNSW 图结构不兼容。**

HNSW 图的邻居关系基于原始空间的 L2 距离。PQ ADC 在旋转空间中计算距离会改变邻居排序，导致图搜索走向错误方向。Fine rerank 读原始 vecblocks 验证，但候选集已经错了。

要使 OPQ 工作，需要：
1. 在旋转空间中重建 HNSW 图（全量重建索引）—— 成本极高
2. 或者只在 PQ 粗筛阶段用 OPQ 距离，但保持图遍历用原始空间距离 —— 需要双空间距离计算，复杂度大

### 结论
**OPQ 方案在不重建索引的情况下不可行。** M=24 PQ 质量上限 94.05% 是当前框架的硬约束。

提升 PQ 质量的替代方向：
- 更大 codebook（M=32 + 更多训练迭代）—— 边际收益小
- 残差编码 —— 复杂度高
- 接受 94% recall 放宽 SLA —— 另开 process 提案
