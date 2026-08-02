# Proposal: 4T Scaling 排查 - Post thread_local Fix

> track: poc
> 关联: [[DEC-063]]、[[DEC-064]]、[[BEH-021]]、[[CON-SLA-013]]、[[CON-POC-001]]
> 日期: 2026-08-02
> Status: Pending

## 1. 问题陈述

DEC-063 记录的 4T 数据（R1 4T=249.4, 0.89x of 1T=279.3）是 thread_local 修复**之前**、
且为 **pre-memopt** 的相对对比（Buffered+EVICT）。

- commit `7742330`：`pipe_piped_pages_` / `pipe_page_bufidx_` → thread_local
- [[DEC-064]]：内存优化已 promote；post-memopt 后 1T 上 pipe 无收益；cgroup 下限可至 **3GB**

**仍缺**：post-memopt + thread_local 后的 **4T** 完整矩阵（R0/R1），用于确认 scaling 与
pipe 是否在多线程下仍无收益。

## 2. 排查计划

### Phase 1: Post-fix 4T Benchmark

**环境**: DEEP10M (10M/96D), **3GB 或 5GB** cgroup（post-memopt 3GB 已可跑，见 [[DEC-064]]）,
10000 queries, k=10, ef=300, REFINE_EF=300  
**Binary**: build/benchmark_pipe（thread_local + 与 Trunk 对齐的内存优化）

| 轮次 | 配置 | 环境变量 |
|------|------|----------|
| R0 1T | baseline | FINE_BUFFERED=1 FINE_PREAD=1 EVICT_PAGE_CACHE=1 |
| R0 4T | baseline | + NUM_THREADS=4 |
| R1 1T | + pipe_ring_ | + PIPE_FINE=1 |
| R1 4T | + pipe_ring_ | + PIPE_FINE=1 NUM_THREADS=4 |

**目标（探索，非 Trunk SLA）**: 记录 scaling；若 R1≈R0，与 [[DEC-064]] 1T 结论一致即可关闭 pipe 4T 疑点。

### Phase 2: 瓶颈定位（若 baseline 4T scaling < 2.5x）

候选：BlockCache mutex、pread/VFS、分配器、GraphPrefetcher mutex、io_uring 内核竞争。

### Phase 3: 修复（仅 `poc/`）

按 Phase 2 数据再提案；不改 Trunk `src/`（除非另开 promote/bug）。

## 3. 不做的事

- 不改 `src/` 生产代码（本提案）
- 不改 stable SLA
- 不引用 pre-memopt / pre-thread_local 4T 作为现行决策依据
- 不把 Buffered+EVICT 相对数字写成 [[CON-SLA-013]] O_DIRECT 辅表达标
