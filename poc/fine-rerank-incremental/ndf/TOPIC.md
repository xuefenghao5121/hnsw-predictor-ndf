# TOPIC: fine-rerank-incremental

> topic_id: fine-rerank-incremental
> status: exploring
> baseline_protocol: [[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]] (sustained)
> baseline_trunk_sha: e06ef31
> baseline_status: current
> explore_surface: io-path,fine-rerank
> depends_on_topics: pipeline-param-retuning (promoted, DEC-087)
> conflicts_with_topics: []
> binder: [[DEF-022]]
> opened: 2026-08-09

## 目标

分批增量 pread + 批间早终止，减少 Phase B I/O 总量。

与 DEC-081（rejected）的根本区别：DEC-081 先读全部后终止（省计算），
本提案边读边停（省 I/O）。

## 基线

M=16 EF=65, 256MB cgroup, 1T, sustained (N=1000 R=15 seed=42):
- agg QPS: 2,483
- recall: 95.52%
- recall 余量: 0.52pp

> baseline 来自 DEC-087 R0'-R4' redo (CON-SLA-020 口径)

## Active hypothesis

候选已按 PQ 距离升序排列。最接近 query 的候选大概率在精确 top-K 中。
分批读取前 B 个候选，如果 top-K 已稳定，剩余候选的 I/O 可以跳过。

## 核心风险

recall 余量仅 0.52pp，早终止必须保守。SIFT1M PQ 距离分布无明显拐点（DEC-081）。

## 实验计划

| 阶段 | 内容 | 验收 |
|------|------|------|
| R0 | 基线验证（Trunk benchmark_sustained，不改代码） | agg ≈ 2,483 ± 5% |
| R1 | 增量 pread（FINE_INCREMENTAL=1, 无早终止）, B={8,16,32} | QPS 变化 ±5% 内 |
| R2 | 批间早终止, margin={1.5,1.2,1.0}, streak={5,10,20} | Pareto 前沿 |
| R3 | WILLNEED lookahead={0,1,2} | 最优组合 |
| R4 | 最优组合完整验证 | recall ≥ 95%, QPS vs R0 |

## 标准配置 (对齐 CON-SLA-020 + DEC-087)

```bash
CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
FLAT_VEC_MB=64 ADAPTIVE_EF=0
REFINE_EF=65  # M=16 最优 (DEC-087)
```

## 写入边界

- MUST NOT 修改 Trunk `src/`、`include/`、`tests/`
- 在 `poc/fine-rerank-incremental/` 下编译独立 benchmark
- 可只读链接 Trunk `src/core/*.cpp` 和 `include/`
- 改动仅在 POC 目录内的修改副本

## 与 DEC-081 的关系

| | DEC-081 (rejected) | 本主题 |
|--|-------------------|--------|
| 读取模式 | 全量批量 pread | 分批增量 pread |
| 早终止时机 | 读完全部后 | 批之间 |
| 节省 | L2 计算 (ns) | pread I/O (us) |
