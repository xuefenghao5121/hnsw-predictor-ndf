# DEC-090: Fine Rerank 增量早终止负结果 {#DEC-090}

> date: 2026-08-09
> affects: DEC-081, DEC-088
> Rejects: fine-rerank-incremental
<!-- ndf: depends-on=DEC-088 -->

## Context

DEC-081 曾尝试 Fine Rerank 早终止，因「先批量读后终止，只省计算不省 I/O」而 rejected。
本 POC 尝试「分批增量 pread + 批间早终止」，在批之间省 I/O。

## 实验

M=16 EF=65, 256MB cgroup, 1T, sustained (N=1000 R=15 seed=42)

| 配置 | Agg QPS | Recall | vs R0 | ≥95%? |
|------|---------|--------|-------|-------|
| R0 baseline (strict) | 1,480 | 95.52% | — | ✅ |
| R1 inc B=16 no-stop | 1,461 | 95.52% | -1.3% | ✅ |
| R2 B=8 early-stop | 1,512 | 94.51% | +2.2% | ❌ |
| R2 B=16 early-stop | 1,487 | 95.28% | +0.5% | ✅ |
| R2 B=16 streak=10 | 1,494 | 95.28% | +0.9% | ✅ |
| R2 B=16 streak=20 | 1,492 | 95.28% | +0.8% | ✅ |

## 根因

与 DEC-081 一致：SIFT1M 候选 PQ 距离分布平坦，无明显拐点。
前 k 个候选大概率进入 top-K（batch_hits > 0），margin 条件不触发。
即使触发，仅省 ~15-20 个 pread，被 batch 开销抵消。

## 结论

增量 pread + 早终止在 SIFT1M 下无显著收益（+0.5~0.9% agg QPS）。
方向与 DEC-081 一致，根因相同。

> source: poc/fine-rerank-incremental/ndf/evidence/r1-r2-incremental-earlystop-20260809.md
