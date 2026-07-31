# Proposal: Read Coalescing - 候选页合并读取

> 日期: 2026-07-31
> 关联: DEC-060 方向 1 (★★★ 最高优先级)
> 场景: 场景1 增量特性
> Status: Implemented on 2026-07-31
> 修订: 2026-07-31 — SLA/范围与固定目录对齐（仅 pread；QPS≥115；去掉未测 ≥160）

## 背景

DEC-060 方向 1：Fine Rerank 的 ~100 个候选分散在不同 4KB 页上，每页一次 pread。
但 BFS 重排后图相邻节点物理相邻，多个候选可能落在同一个 64KB block（16 页）内。
当前代码逐页 pread，未利用这种局部性。

**核心思路**：收集候选的 page 号 -> 按 block_id 分组 -> 密集 block 一次读 64KB ->
在内存中提取所需 4KB 页 -> 稀疏候选仍用 4KB pread。

## 已落地 L1 条款（固定目录为准）

| ID | 文件 | 要点 |
|----|------|------|
| [[BEH-017]] | `20-behavior/fine-rerank.md` | **仅** `FINE_PREAD=1`；`refines=BEH-001` |
| [[BEH-017-L2]] | 同上 | pread 机制 |
| [[API-009]] | `30-interfaces/env.md` | env；前置 `FINE_RERANK`+`FINE_PREAD`；不 refine API-007 |
| [[CON-SLA-012]] | `40-constraints/sla.md` | O_DIRECT+pread：QPS≥115，Recall≥95% |
| [[VER-017]] | `50-verification/acceptance.md` | 验收表 |
| [[DEF-019]] | `00-charter/glossary.md` | 术语 |

### 实测（pread, SIFT1M, 512MB, O_DIRECT, 1T）

| REFINE_EF | Recall | 基线 QPS | Coalesce QPS | 提升 |
|-----------|--------|---------|-------------|------|
| 200 | 97.20% | 60.9 | 66.5 | +9.2% |
| 100 | 95.75% | 110.9 | 118.2 | +6.6% |
| 80 | 94.90% | 133.3 | 141.6 | +6.2% |

初估 +30% **未达标**；后续优化转 io_uring（见 `proposal-read-coalescing-v2.md`，Pending）。

## refines / depends-on

- `BEH-017` `refines=BEH-001` `depends-on=DEC-060,API-009`（禁止 `refines=BEH-007` L2）
- `CON-SLA-012` `refines=CON-SLA-011`
- `depends-on: DEC-060`

## 非本提案范围

- io_uring 路径 Read Coalescing（v2）
- 将 aspirational ≥160 QPS 写入 must SLA
