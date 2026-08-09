# TOPIC: param-expansion-sweep

> topic_id: param-expansion-sweep
> status: exploring
> baseline_protocol: [[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]] (sustained)
> baseline_trunk_sha: 054ff92
> baseline_status: current
> explore_surface: tuning,io-path
> depends_on_topics: framework-driven-optimization (promoted, DEC-091)
> conflicts_with_topics: []
> binder: [[DEF-022]]
> opened: 2026-08-09

## 目标

展开 DEC-088 决策树中未覆盖的参数，建立全参数性能图谱。

## 实验计划

| 阶段 | 参数 | 扫描值 | 基线配置 |
|------|------|--------|---------|
| R0 | FLAT_VEC_MB | 32,64,96,128,160 | M=16 EF=65 |
| R1 | CACHE_MB | 32,64,96,128 | M=16 EF=65 |
| R2a | ADAPTIVE_EASY_EF | 35,40,45,50 | M=16 EF=65/80, M=24 EF=60 |
| R2b | ADAPTIVE_EASY_GAP | 1.003-1.020 | M=16 EF=80 |
| R3 | M=24 block size | 32K vs 64K | M=24 EF=60 |
| R4 | 最优组合 | 全部最优 | 叠加验证 |

## 标准配置 (同 framework-driven-optimization)

```bash
CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
FLAT_VEC_MB=64 ADAPTIVE_EF=0
```

## 写入边界

- MUST NOT 修改 Trunk src/ include/ tests/
- 使用 Trunk build/benchmark_sustained
