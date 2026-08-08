# TOPIC: block-size-tuning

> topic_id: block-size-tuning
> status: exploring
> baseline_protocol: [[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]] (sustained)
> baseline_trunk_sha: 29b0135
> baseline_status: current
> explore_surface: block-layout,io-path
> depends_on_topics: pipeline-param-retuning (promoted)
> conflicts_with_topics: []
> binder: [[DEF-022]]
> opened: 2026-08-08

## 目标

在最优配置 (M=16 EF=65) 下验证 block size 对 sustained 性能的影响，
扫描 {16K, 32K, 48K, 64K, 128K} 找最优 block size。

## 背景

pipeline-param-retuning R4' 发现 32K vs 64K: +52.5% QPS (M=24 EF=60 1T)。
但未在 M=16 EF=65 (最优配置) 上验证，未测试 16K/48K，未做多线程。

## Active hypothesis

32K block size 通过更细的 I/O 粒度提升 page cache 利用率，
在 M=16 EF=65 256MB cgroup 下仍有显著收益。

## 实验计划

| 阶段 | 内容 | 验收 |
|------|------|------|
| R0 | M=16 EF=65, BS={32K,64K,128K} 1T BASE | Pareto 前沿 |
| R1 | M=16 EF=65, BS={16K,48K} 1T BASE | 补全扫描 |
| R2 | 最优 BS × T={4,16} | 多线程验证 |
| R3 | 最优 BS + ADAPTIVE | ADAPTIVE 组合 |

## 标准配置 (对齐 CON-SLA-020 + DEC-087)

```bash
CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
FLAT_VEC_MB=64 ADAPTIVE_EF=0
REFINE_EF=65  # M=16 最优 (DEC-087)
```

## 写入边界

- MUST NOT 修改 Trunk `src/`、`include/`、`tests/`
- build_pipeline.sh 复制到 `poc/block-size-tuning/` 修改 BS
- 不同 BS 数据放在 `output/sift1m_m16_bs{size}/`
