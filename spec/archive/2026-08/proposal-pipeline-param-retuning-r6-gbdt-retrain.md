> track: poc
> topic: pipeline-param-retuning (amend - R6)
> status: proposal
> 日期: 2026-08-08

# 提案: R6 - 重训 GBDT 模型 (256MB cgroup + 新 EF 配置)

## 背景

### 现有 GBDT 模型的问题

1. **gbdt-retrain/gbdt_model.h**: 训练于 M=16 EF=200 @ 512MB，用官方 10K query 池（无 self-match）
   - R4 测试 (512MB EF=100): +12-34% QPS vs BASE ✅
   - 但未在 256MB + EF=65/60 下测试
2. **pipeline-param-retuning/gbdt_model_m24.h**: 训练于 M=24 EF=200
   - R1' 测试 (256MB EF=60): -0.8% vs BASE（噪声内，无效）
   - 根因：EF=200 训练的标签在 EF=60 下不适用

### 需要重训的原因

GBDT 预测的是 Phase B 最小候选数 `min_n`，这个值取决于：
- **Phase A 候选集质量**（受 M_graph 和 EF 影响）
- **PQ 近似距离排序质量**（受 M_pq 影响）
- **query 难度**（query 本身特性）

EF=200 -> EF=65 时，Phase A 返回的候选集更小且排序不同，`min_n` 分布会变化。
旧模型的预测在新配置下失准。

## 实验计划

### R6.1: Profiling (生成训练数据)

对两个目标配置运行 `benchmark_llsp` + `PROFILE_LLSP=1`：

| 配置 | M_graph | EF | cgroup | query pool | GT |
|------|---------|-----|--------|-----------|-----|
| M=16 EF=65 | 16 | 65 | 256MB | 官方 10K | 官方 |
| M=24 EF=60 | 24 | 60 | 256MB | 官方 10K | 官方 |

输出: `/tmp/llsp_r6_{m16,m24}.txt` (每 query 的候选距离 + ID dump)

### R6.2: 特征提取 + 标签生成

用 `analyze_r0.py` 从 profiling dump 提取：
- 特征: n_coarse, d0, d9, dk, dk1, gap_ratio, d_mean, d_std, d_cv, d_ratio_01, d_ratio_09
- 标签: min_n (每个 query 达到 recall@10 ≥ 95% 的最小候选数)
- 用官方 GT 计算标签（无 self-match）

### R6.3: 训练 LightGBM 模型

- 参数: 与 train_r2.py 一致 (100 棵树, max_depth=4, num_leaves=15)
- 训练两个模型: `gbdt_model_m16_ef65.h` 和 `gbdt_model_m24_ef60.h`
- 导出 C++ if-else 规则表

### R6.4: Sustained benchmark 验证

三方对比 (256MB cgroup, CON-SLA-020 金标配置):

| Config | 模式 | 对比 |
|--------|------|------|
| M=16 EF=65 | BASE | 基线 |
| M=16 EF=65 | ADAPTIVE (eef=40) | DEC-086 最优 |
| M=16 EF=65 | **GBDT-v3** | 新模型 |
| M=24 EF=60 | BASE | 基线 |
| M=24 EF=60 | ADAPTIVE (eef=40) | DEC-086 最优 |
| M=24 EF=60 | **GBDT-v3** | 新模型 |

测试 1T + 16T，共 12 个配置。

## 验收标准

1. GBDT-v3 recall ≥ 95% (sustained)
2. GBDT-v3 QPS > BASE + 5%
3. GBDT-v3 QPS ≥ ADAPTIVE
4. 模型导出 C++ header < 500KB

## 写入边界

- 仅 `poc/pipeline-param-retuning/`：训练脚本 + 模型 + evidence
- **不改 Trunk `src/`**（[[BEH-018]] 第 6 条）
- **不改 stable 条款**（[[CON-POC-001]]）
- GBDT 模型不写入 `spec/models/`（[[ARCH-008]]）
