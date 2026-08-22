> track: poc
> topic: block-size-tuning (new, depends on pipeline-param-retuning)
> status: proposal
> 日期: 2026-08-08

# 提案: block-size-tuning - Block Size 调优 POC

## 背景

pipeline-param-retuning (promoted, [[DEC-087]]) R4' 发现 block size 32K vs 64K +52.5% QPS，
但延期未深入验证。本 POC 独立探索 block size 对 sustained 性能的影响。

## 依赖

- `depends_on_topics`: pipeline-param-retuning (promoted)
- `baseline_protocol`: [[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]] (sustained 金标)
- `baseline_trunk_sha`: 29b0135 (pipeline-param-retuning promote tip)

## 目标

1. 在最优配置 (M=16 EF=65) 下验证 32K block size 的收益
2. 扫描 block size = {16K, 32K, 48K, 64K, 128K} 找最优
3. 多线程 (1T/4T/16T) 验证
4. 评估是否需要修改 `build_pipeline.sh` 默认 BS

## 假设

block size 越小 -> 每次读取的 page 越少 -> I/O 粒度更细 -> page cache 利用率更高。
但太小（如 16K）可能导致元数据开销增大。

## 实验计划

| 阶段 | 内容 | 数据准备 | 验收 |
|------|------|---------|------|
| R0 | M=16 EF=65, BS={32K, 64K, 128K} 1T BASE | 重建 M=16 bs32k, bs128k | Pareto 前沿 |
| R1 | M=16 EF=65, BS={16K, 48K} 1T BASE | 重建 M=16 bs16k, bs48k | 补全扫描 |
| R2 | 最优 BS × T={4, 16} | - | 多线程验证 |
| R3 | 最优 BS + ADAPTIVE | - | ADAPTIVE 组合 |

## 写入边界

- 本 POC MUST NOT 修改 Trunk `src/`、`include/`、`tests/`
- `build_pipeline.sh` 是 Trunk 文件 -> 复制到 `poc/block-size-tuning/` 修改 BS
- 不同 BS 的数据放在 `output/sift1m_m16_bs{size}/`
- 使用 Trunk `build/benchmark_sustained`

## 表面冲突检查

explore_surface: block-layout, io-path
- pipeline-param-retuning (promoted): block-layout 已探索但延期 -> 不冲突，依赖关系
- 无其他活跃 exploring 主题相交

## 数据准备

已有数据：
- M=24 bs{16k,32k,64k,128k} (来自 pipeline-param-retuning R4')
- M=16 bs64k (Trunk 默认)

需新建：
- M=16 bs{16k,32k,48k,128k} (用修改后的 build_pipeline.sh 重建 Step 4-5)

> source: poc/pipeline-param-retuning/ndf/evidence/r0-r4-redo-20260808.md (R4' block size 结论)
> track: poc ; Topic: block-size-tuning
