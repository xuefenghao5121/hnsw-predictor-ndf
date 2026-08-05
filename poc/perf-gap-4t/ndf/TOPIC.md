# TOPIC: perf-gap-4t

> topic_id: perf-gap-4t
> status: exploring
> created: 2026-08-05
> baseline_protocol: [[CON-SLA-014]] + SIFT1M@512MB + 4T
> depends_on_topics: [multi-thread-scaling]

## 概述

在 SIFT1M 4T 512MB cgroup 约束下，缩小 DiskHNSW 与 hnswlib(unlimited) 的性能差距。
临时基线：DiskHNSW 9657 QPS / 95.80% recall vs hnswlib 18496 QPS / 98.30% recall。

## 临时基线 (SIFT1M 4T)

| 指标 | DiskHNSW (512MB cgroup) | hnswlib (unlimited) | 差距 |
|------|------------------------|--------------------|----|
| QPS | 9,657 | 18,496 | 52% |
| Recall@10 | 95.80% | 98.30% | -2.5pp |
| P99 | 0.89ms | 0.37ms | 2.4x |
| 内存 | 512MB (cgroup: anon~202MB + file~308MB) | 732MB (RSS: 全 anon) | 70% |

> 内存对比基于 cgroup 限制（DiskHNSW）vs RSS（hnswlib），不是 RSS-only 对比。
> DiskHNSW 的 page cache (~308MB) 是其运行所必需的，计入 cgroup 预算。

## Proposals

| Path | Status | Role |
|------|--------|------|
| `spec/open/proposal-perf-gap-4t.md` | Pending | root |

## Draft Clauses

无（本 POC 不新增 must 条款，仅收集证据）

## Active Hypothesis

1. **H1**: flat_vec_cache 调大可减少 FineRerank I/O，提升 QPS >5%
2. **H2**: PQ M=48/64 可提升 recall >1pp，同时可能提升 QPS
3. **H3**: FineRerank 候选页批量 pread 可减少 syscall 开销
4. **H4**: VisitedList 池化可减少 4T 下 5% memset 开销

## 探索方向

| ID | 方向 | 复杂度 | 预期 | 状态 |
|----|------|--------|------|------|
| 1 | flat_vec_cache 调优 (64/96/128/160/192MB) | 低 | +5-15% QPS | pending |
| 2 | PQ 质量 (M=48/64, OPQ) | 中 | +1-2pp recall | pending |
| 3 | FineRerank I/O (批量 pread, 页合并) | 中高 | +5-10% QPS | pending |
| 4 | VisitedList 池化 | 中 | +3-5% QPS | pending |
| 5 | ef/refine_ef 调优 | 低 | trade-off | pending |

## Evidence

(empty)

## Next Gate

确认后开始方向 1（flat_vec_cache 调优，最低复杂度快速验证）

## Notes

- 所有代码变更在 `poc/perf-gap-4t/` 内，不修改 Trunk `src/`
- 基线测量对齐 [[CON-SLA-014]]（drop_caches + 512MB cgroup）
- 对标 hnswlib unlimited 4T = 18496 QPS / 98.30% recall / 732MB RSS
- 从 multi-thread-scaling POC 继承差距来源分析
