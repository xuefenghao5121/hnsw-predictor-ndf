# 提案：gbdt-retrain - 用官方 query 池重新训练 GBDT 模型

> track: poc
> explore_surface: search-adaptive,learned-pruning,fine-rerank
> 提出日期：2026-08-07
> 基线 Trunk：`7c91280`
>
> Status: Proposed

## 1. 背景与动机

### 1.1 原 GBDT POC 失败回顾

`gbdt-learned-pruning` POC 的 GBDT 模型在 sustained 口径下收益不成立（-0.9~+1.8%，噪声内）。
根因是训练数据来自 base-sampled 10K query，存在 self-match 污染：

- query 从 `sift_base.fvecs` 随机抽取 -> query 本身在 base 中
- brute-force GT top-1 恒为 self（距离 0）
- 模型学到的 min_n 系统性偏低（query "异常容易"）
- 用在官方 query 上预测失准 -> 收益归零

已据此将 [[BEH-034]] 从 `must` 降级为 `may`（[[DEC-084]]）。

### 1.2 复活条件

[[BEH-034]] 正文明确：
> "用合规 query 池重新 profiling 并重训模型，在 sustained 口径下重测。
> 若确认收益可发提案重新升为 must。"

### 1.3 已具备的条件

- ✅ 官方 SIFT 10K query 池（`data/sift_query_official10k.fvecs`）
- ✅ 官方 GT（`data/sift_groundtruth_official.ivecs`，10000×100）
- ✅ Sustained benchmark 工具（`build/benchmark_sustained`）
- ✅ 原 POC 的 profiling 代码（`poc/gbdt-learned-pruning/disk_hnsw_llsp.cpp`）
- ✅ 原 POC 的训练脚本（`poc/gbdt-learned-pruning/train_r1.py`）

## 2. 方案设计

### 2.1 核心改动

**唯一根因修复**：用官方 query 池替代 base-sampled query 做 profiling。

| 维度 | 原 POC | 本 POC |
|------|--------|--------|
| query 来源 | `sift_base.fvecs` 随机抽样 | `sift_query_official10k.fvecs` 官方池 |
| GT | 自行 brute-force（含 self） | `sift_groundtruth_official.ivecs` 官方 |
| 测量口径 | 200q cache-warmed | sustained（N=1000, R=15, 禁预热） |

### 2.2 Profiling 方案

复用原 POC 的 `PROFILE_LLSP=1` 机制（`disk_hnsw_llsp.cpp` 已实现）：

1. 用 `benchmark_llsp` 跑官方 10K query 池（单线程, EF=200, 无 cgroup 限制）
2. `PROFILE_LLSP=1` 输出每个 query 的：候选 ID 列表 + PQ 距离分布特征
3. 用官方 GT 计算标签：min_n = 包含全部 10 个 GT 的最小候选数

### 2.3 训练方案

与原 POC 相同参数（便于对比）：
- LightGBM, 100 棵树, max_depth=4
- 11 维特征（n_coarse, d0, d9, dk, dk1, gap_ratio, d_mean, d_std, d_cv, d_ratio_01, d_ratio_09）
- 80/20 训练/测试划分
- 导出 C++ if-else 规则表

### 2.4 验证方案

sustained 三方对比（与 comprehensive_sweep 同协议）：

| 配置 | 模式 | 说明 |
|------|------|------|
| 256MB / 512MB × 1/4/16T | BASE | 固定 EF=100 |
| 同上 | ADAPTIVE | `ADAPTIVE_EF=1`（sustained 已验证 +12.5~31.4%） |
| 同上 | GBDT-v2 | 新模型 + `LEARNED_EF=1` |

N=1000, R=15, seed=42，严格 cgroup 隔离。

## 3. 预期结果

### 3.1 乐观情况

GBDT-v2 在 sustained 下：
- recall ≥ 95%
- QPS 收益 > ADAPTIVE（+12.5~31.4%）
- 结论：GBDT 多特征建模确实优于单特征启发式 -> 升回 must

### 3.2 中性情况

GBDT-v2 有收益但不如 ADAPTIVE：
- QPS > BASE + 5%，但 < ADAPTIVE
- 结论：保留 may，定位为 fallback

### 3.3 悲观情况

GBDT-v2 仍无收益（-5~+5%）：
- 结论：PQ 距离特征对候选数预测的信息量有限，ADAPTIVE 已提取主要信号
- BEH-034 维持 may，永久标注"需跨数据集验证泛化性"

## 4. 不做的事

- 不改 Trunk `src/`（POC 阶段）
- 不改 `include/gbdt_model.h`（POC 阶段用 `poc/gbdt-retrain/gbdt_model.h`）
- 不引入新特征（保持 11 维，便于对比）
- 不改 LightGBM 参数（保持 100 棵树, depth=4）
- 不在 200q cache-warmed 下评估（只看 sustained）

## 5. 表面冲突检查

活跃 exploring 主题：无（sustained-query-benchmark 已 promoted）。

本主题 `explore_surface: search-adaptive,learned-pruning,fine-rerank`：
- 与已 promoted 的 `helmsman-adaptive`（同 surface）为**继任关系**，非竞争
- 与已 promoted 的 `gbdt-learned-pruning`（同 surface）为**修复关系**
- 与已 promoted 的 `sustained-query-benchmark`（surface: test-infra）为**依赖关系**（本 POC 依赖其测量工具）
- 判定：**不冲突**

## 6. 影响的既有条款

| 条款 | 影响 |
|------|------|
| [[BEH-034]] | 若成功：may -> must，更新收益声明；若失败：维持 may |
| [[API-018]] | 若成功：更新收益状态标注 |
| [[DEC-084]] | 追加复活记录（无论成败） |

POC 阶段 MUST NOT 修改以上 stable 条款。

## 7. 晋升条件

若以下全部满足，另开 promote 提案：

1. recall ≥ 95%（sustained，官方 GT）
2. GBDT-v2 QPS > BASE + 5%（sustained，统计显著）
3. 同 seed 可复现（±3%）
4. margin 调优完成，最优值确定

若 GBDT-v2 ≤ BASE + 5% -> 走 §6.2d 负结果闭环，BEH-034 维持 may。
