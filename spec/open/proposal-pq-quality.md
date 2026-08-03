# Proposal: 改善 PQ 质量 {#PROP-PQ-QUALITY}

> track: poc
> Status: Draft
> 日期: 2026-08-03
> 关联: [[CHR-006]], [[CON-SLA-014]], [[DEC-067]], [[BEH-024]]
> 基线: DEEP10M 2GB cgroup Buffered 1T = 580 QPS, majfault=73005

## 动机

DEEP10M 使用 PQ M=32, dsub=3, nbits=8。PQ 粗筛产生大量 false positive 候选，
每个 false positive 都需要 fine rerank 读 4KB 页。改善 PQ 质量可减少 false positive，
直接减少 I/O 量。

## 探索方向

| 方向 | 描述 | 预期效果 |
|------|------|----------|
| M=48/64 | 增大 PQ 码本 | 更精确的粗筛, 更少 false positive |
| dsub=4/6 | 增大子空间维度 | 更好的子空间划分 (当前 dsub=3 for 96D) |
| OPQ 旋转 | 优化PQ 旋转矩阵 | 减少子空间间相关性 |
| retrain | 用更大数据训练 | 更好的码本覆盖 |

目标：在不增加 PQ codes 内存（304MB）太多的前提下，减少 fine rerank 候选数。

## 验证协议

- CON-SLA-014 严格隔离, 2GB cgroup
- R0: 当前 PQ (M=32, dsub=3) 基线
- R1: M=48 (448MB codes)
- R2: M=64 (608MB codes)
- R3: dsub=4 (需 retrain)
- 监控: recall, QPS, majfault, 候选数

## 非目标

- 不改 REFINE_EF（与 refine-ef POC 独立）
- 不改搜索算法
- 不改 cgroup 限制
