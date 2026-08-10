# DEC-095: Promote CQE Peeking — Completion-Order Fine Rerank
<!-- ndf: kind=decision id=DEC-095 level=3 status=accepted date=2026-08-10 -->
<!-- ndf: affects=BEH-036,API-020 depends-on=DEC-071,CON-SLA-014 -->
<!-- ndf: source=poc/ssd-parallelism-io/ ; track=promote ; Topic: ssd-parallelism-io -->
<!-- ndf: Promotes: ssd-parallelism-io -->

## Context

基于 VLDB 2025 "Turbocharging Vector Databases using Modern SSDs" 论文中的
CQE peeking 概念，在 DiskHNSW Fine Rerank io_uring 路径中实现完成顺序处理。

## POC 证据 (R0-R3)

| 轮次 | 配置 | 结果 |
|------|------|------|
| R0 | 1T A/B baseline | CQE peeking +3.5% agg QPS |
| R1 | 1T/4T/16T scaling | +3.5%/+3.2%/+1.0% (递减) |
| R2 | 1T profile | I/O wait −37%, Fine −5%, compute −71% |
| R3 | submit 优化 | −12% (irreducible without SQPOLL) |

## Decision

**Accept**: Promote CQE peeking into Trunk.

1. `vec_ring_` → `thread_local`（per-thread io_uring，多线程安全）
2. 批量屏障 → CQE peeking with page→cands index
3. `FINE_CQE_PEEK` toggle (default 1, set 0 for legacy)
4. Lazy init: per-thread io_uring ring created on first use

### 不要
- Registered buffers/FD (R3 负结果)
- SQPOLL (requires CAP_SYS_ADMIN)
- New SLA clause (behavior-only change, no config/constraint change)

### 延期
- L3 semantic core: simple completion-order change, model can be added in follow-up
