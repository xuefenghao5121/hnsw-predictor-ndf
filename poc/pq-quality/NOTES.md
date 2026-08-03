# POC: PQ Quality

> 提案: `spec/open/proposal-pq-quality.md`（Implemented）
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
