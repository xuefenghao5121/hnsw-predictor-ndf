> track: poc
> topic: param-expansion-sweep
> status: draft
> 日期: 2026-08-09

# 提案: DEC-088 决策树全参数展开扫描

## 背景

framework-driven-optimization (DEC-091) 完成了决策树步骤 1-4 的验证，但以下参数未展开：

- **FLAT_VEC_MB** (FVC): 热向量 LRU 大小，框架预测 agg/steady 存在权衡
- **CACHE_MB**: BlockCache 元数据，框架预测 ±2-5% 噪声
- **ADAPTIVE_EASY_EF/GAP**: 自适应参数细调，不同 recall 预算下的最优值
- **M=24 block size**: page cache 覆盖率 4.8% < 5%，框架预测 block size 有效
- **M=24 +ADAPTIVE**: recall 预算 1.60pp，框架预测 +68% 增益

## 依赖

- `depends_on_topics`: framework-driven-optimization (promoted, DEC-091)
- `methodology`: [[DEC-088]] 调优决策树
- `baseline`: M=16 EF=65 agg=1,486 QPS / recall=95.52% (DEC-091)

## 写入边界

- MUST NOT 修改 Trunk `src/`、`include/`、`tests/`
- 使用 Trunk `build/benchmark_sustained`
- 所有脚本在 `poc/param-expansion-sweep/` 下

## 实验计划

### R0: FLAT_VEC_MB 扫描 (B 类参数)

基线: M=16 EF=65, FLAT_VEC_MB = {32, 64, 96, 128, 160}
- 框架预测: 大 FVC 提升 steady QPS（热向量命中率高），但吃 page cache 伤害 agg
- 256MB cgroup: page cache = 256 - 229 = 27MB，FVC 每增大 32MB 吃 ~12% page cache
- 假设: 最优点在 64-96MB

### R1: CACHE_MB 扫描 (C 类参数)

基线: M=16 EF=65, CACHE_MB = {32, 64, 96, 128}
- 框架预测: ±2-5% 噪声
- 假设: 无显著差异

### R2: ADAPTIVE 参数展开 (E 类参数)

#### R2a: ADAPTIVE_EASY_EF × recall 预算
- M=16 EF=65 (预算 0.52pp): eef={35, 40, 45}
- M=16 EF=80 (预算 1.79pp): eef={35, 40, 45, 50}
- M=24 EF=60 (预算 1.60pp): eef={35, 40, 45, 50}

#### R2b: ADAPTIVE_EASY_GAP 扫描
- 基线: M=16 EF=80, gap = {1.003, 1.006, 1.010, 1.015, 1.020}
- 框架预测: gap 越小越激进（更多 query 被分类为 easy），recall 降更多

### R3: M=24 Block Size (步骤 5)

- M=24 EF=60, block_size = {32K, 64K}
- 框架预测: 32K 应有效 (覆盖率 4.8% < 5%)
- 注意: 需要构建 M=24 32K vecblocks 文件

### R4: 最优组合验证

将各参数最优值组合，验证是否有叠加效应。

## cgroup 有效性校验

每组结束后抽样验证 pgmajfault > 0 (独立验证脚本)

> source: spec/decisions/24-tuning-framework.md (DEC-088) ; spec/decisions/27-framework-driven-optimization-results.md (DEC-091)
> track: poc ; Topic: param-expansion-sweep
