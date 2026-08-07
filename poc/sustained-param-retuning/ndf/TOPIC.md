# TOPIC: sustained-param-retuning

> topic_id: sustained-param-retuning
> status: promoted
> baseline_protocol: [[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]] (sustained)
> baseline_trunk_sha: bd52c80
> baseline_status: current
> explore_surface: search-adaptive,refine-ef,cache-tuning
> depends_on_topics: sustained-query-benchmark (promoted), gbdt-retrain (promoted)
> conflicts_with_topics: []
> binder: [[DEF-022]]
> opened: 2026-08-07

## 目标

在 sustained 口径下重新扫描主线参数最优值，替换 200q cache-warmed 确定的旧最优值。

## 背景

除 GBDT_MARGIN 外，所有主线参数（REFINE_EF, FLAT_VEC_MB, ADAPTIVE 阈值,
VL_POOL_THREADS, CACHE_MB）均来自 200q cache-warmed 口径。
sustained 下 I/O 是主瓶颈，且 recall 余量更大（96.00% vs 95.75%），
200q 下被否的激进参数可能可行。

## Active hypothesis

sustained 下最优参数组合 != 200q 最优参数组合，
新组合在 recall ≥ 95% 约束下 QPS 优于旧组合。

## 实验计划

| 轮次 | 内容 | 验收 |
|------|------|------|
| R0 | REFINE_EF 扫描 {60,70,80,90,100,120} × 512/256MB × 1/4/16T | 找 Pareto 前沿 |
| R1 | ADAPTIVE 阈值重校准 (easy_ef/gap) | recall ≥ 95%, QPS > 旧阈值 |
| R2 | FLAT_VEC_MB 重扫描 | sustained 最优值 |
| R3 | 最优组合验证 (完整矩阵) | 新组合 QPS > 旧组合 +5% |
| R4 | VL_POOL + CACHE_MB (如时间允许) | 可选 |

## Draft clauses

无新增条款。本 POC 目标是修改现有 API 默认值（若发现更优参数）。

## 写入边界

- 本 POC MUST NOT 修改 Trunk `src/`（[[BEH-018]] 第 6 条）
- 所有实现在 `poc/sustained-param-retuning/`
- 使用 Trunk `build/benchmark_sustained`，仅改环境变量

## 表面冲突检查

无活跃 exploring 主题。已 promoted 主题与本主题为依赖关系，不冲突。
