# Proposal: Read Coalescing - 候选页合并读取

> 日期: 2026-07-31
> 关联: DEC-060 方向 1 → [[DEC-061]]
> 场景: 场景1 增量特性
> Status: **Rejected / Superseded by DEC-061** (2026-07-31)
> 历史: Implemented on 2026-07-31 → 负结果后代码回退，相关条款 deprecated

## 关闭说明

v1（pread）落地后实测仅 +6–9%；随后 v2（io_uring）实测 −10~16%。
[[DEC-061]] 终止方向 1，删除 `READ_COALESCE*` 实现，并将
[[BEH-017]] / [[API-009]] / [[CON-SLA-012]] / [[VER-017]] / [[DEF-019]] 标为 deprecated。

本文件保留为负结果审计轨迹，**不是**现行 must，也**不是** Pending 实现任务。

## 背景（历史）

DEC-060 方向 1：Fine Rerank 候选按 64KB block 合并读取，期望减少 I/O 次数、抬升 O_DIRECT 地板。

### 历史实测（pread, SIFT1M, 512MB, O_DIRECT, 1T）

| REFINE_EF | Recall | 基线 QPS | Coalesce QPS | 提升 |
|-----------|--------|---------|-------------|------|
| 200 | 97.20% | 60.9 | 66.5 | +9.2% |
| 100 | 95.75% | 110.9 | 118.2 | +6.6% |
| 80 | 94.90% | 133.3 | 141.6 | +6.2% |

初估 +30% 未达标；io_uring 扩展见 `proposal-read-coalescing-v2.md`（同样 Rejected）。
