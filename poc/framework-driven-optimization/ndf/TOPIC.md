# TOPIC: framework-driven-optimization

> topic_id: framework-driven-optimization
> status: exploring
> baseline_protocol: [[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]] (sustained)
> baseline_trunk_sha: 2e0ac9f
> baseline_status: current
> explore_surface: tuning,io-path
> depends_on_topics: pipeline-param-retuning (promoted, DEC-087 数据待修正)
> conflicts_with_topics: []
> binder: [[DEF-022]]
> opened: 2026-08-09

## 目标

用 DEC-088 调优决策树系统性重扫 256MB SIFT1M 1T，消除 DEC-087 cgroup 泄漏数据污染，
找到真实最优配置。

## Active hypothesis

DEC-088 决策树的预测在严格 cgroup 下仍然成立（M=16 低 EF 最优），但具体数字需要修正。

## 实验计划

| 阶段 | 内容 | 决策树步骤 | 验收 |
|------|------|-----------|------|
| R0 | 基线验证 (M=16 EF=100) | — | agg ≈ 1,076 ± 5%, pgmajfault > 0 |
| R1 | M_graph 扫描 | 步骤 2 | Pareto 前沿 |
| R2 | EF 细扫 | 步骤 3 | 找真实拐点 |
| R3 | ADAPTIVE 评估 | 步骤 4 | recall 预算评估 |
| R4 | 最优组合验证 | — | recall ≥ 95%, cgroup 有效 |

## 标准配置

```bash
CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
FLAT_VEC_MB=64 ADAPTIVE_EF=0
```

## cgroup 有效性校验

每个 run MUST 校验:
- pgmajfault > 0
- file_bytes > 0
- violations = 0

## 写入边界

- MUST NOT 修改 Trunk src/ include/ tests/
- 使用 Trunk build/benchmark_sustained
