# TOPIC: gbdt-retrain

> topic_id: gbdt-retrain
> status: ready-for-promote
> baseline_protocol: [[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]] (sustained)
> baseline_trunk_sha: 7c91280
> baseline_status: current
> explore_surface: search-adaptive,learned-pruning,fine-rerank
> depends_on_topics: gbdt-learned-pruning (promoted, demoted), sustained-query-benchmark (promoted)
> conflicts_with_topics: []
> binder: [[DEF-022]]
> opened: 2026-08-07

## 目标

用**合规 query 池**（官方 SIFT 10K，无 self-match）重新 profiling + 重训 GBDT 模型，
在 sustained 口径下验证 LEARNED_EF 收益是否可复活。

## 背景

### 原始 POC 的失败根因（[[DEC-084]]）

原 `gbdt-learned-pruning` POC 的 GBDT 模型训练数据来自 base-sampled 10K query：

1. query 从 `sift_base.fvecs` 随机抽取 -> query 本身在 base 中
2. brute-force GT 的 top-1 恒为 self（距离 0）-> recall 白送 ~10%
3. **训练标签污染**：self-match 使 query "异常容易"，模型学到的 min_n 系统性偏低
4. 用在官方 query 上预测失准 -> `learned_limit` 裁剪失去准确性 -> 收益归零

sustained 实测：GBDT -0.9~+1.8%（噪声内），对比 ADAPTIVE_EF +12.5~31.4%。

### 复活条件（[[BEH-034]] 正文）

> "用合规 query 池（标准 query set，见 [[BEH-035]]）重新 profiling 并重训模型，
> 在 sustained 口径下重测。若确认收益可发提案重新升为 must。"

本 POC 即为执行此复活路径。

## Active hypothesis

用官方 10K query 池重新 profiling + 重训后，GBDT 模型在 sustained 口径下：
- recall ≥ 95%
- QPS 收益 > ADAPTIVE_EF（+12.5~31.4%），否则无升级意义
- 或至少 QPS 收益 > 5%（有统计显著性，非噪声）

## 方案

### 关键改动 vs 原 POC

| 维度 | 原 POC (失败) | 本 POC |
|------|-------------|--------|
| query 池 | base-sampled 10K（有 self-match） | **官方 SIFT 10K**（无 self-match） |
| GT | 自行 brute-force（含 self） | **官方 sift_groundtruth.ivecs** |
| profiling 范围 | 10K query 全部 | **官方 10K 全部**（或子集 N=2000 加速） |
| 测量口径 | 200q cache-warmed | **sustained（N=1000, R=15, 禁预热）** |
| 验收基线 | vs 固定 EF=100 | **vs BASE + vs ADAPTIVE_EF**（三方对比） |

### 执行步骤

1. **R0: Profiling** - 用官方 10K query 跑 `PROFILE_LLSP=1`，收集 per-query 候选特征 + ID
2. **R1: 标签计算** - 用官方 GT 计算每个 query 的 min_n（包含全部 10 个 GT 的最小候选数）
3. **R2: 模型训练** - LightGBM，与原 POC 同参数（100 棵树, depth=4），便于对比
4. **R3: 模型导出** - 导出 C++ if-else 规则表，替换 `gbdt_model.h`
5. **R4: Sustained 验证** - 三方对比：BASE vs ADAPTIVE vs 新 GBDT
   - 256MB + 512MB × 1/4/16T
   - N=1000, R=15, seed=42
6. **R5: margin 调优** - GBDT_MARGIN 扫描 {0.7, 0.8, 0.9, 1.0, 1.1}

### 晋升条件

- recall ≥ 95%（sustained）
- GBDT QPS > BASE + 5%（统计显著，非噪声）
- GBDT QPS ≥ ADAPTIVE（否则 ADAPTIVE 更优，GBDT 无升级意义）
- 若 GBDT < ADAPTIVE 但 > BASE + 5%：保留 may，定位为"ADAPTIVE 不可用时的 fallback"
- 若 GBDT ≤ BASE + 5%：确认无法复活，BEH-034 维持 may

## Draft clauses

无新增条款。本 POC 目标是验证能否将 [[BEH-034]] 从 `may` 升回 `must`。

若成功，修改：
- [[BEH-034]] level: may -> must，更新收益声明
- [[API-018]] 更新收益状态
- [[DEC-084]] 追加复活记录
- 新增 [[DEC-0XX]]: 重训练决策记录

若失败：
- [[BEH-034]] 维持 may
- 新增负结果记录

## 写入边界

- 本 POC MUST NOT 修改 Trunk `src/`（[[BEH-018]] 第 6 条 / [[CON-POC-001]]）
- 所有实现在 `poc/gbdt-retrain/`
- 模型文件替换 `poc/gbdt-retrain/gbdt_model.h`（不直接改 Trunk 的 `include/gbdt_model.h`）
- 若 promote，在 promote 阶段才合入 Trunk

## 数据文件

| 文件 | 说明 |
|------|------|
| `data/sift_query_official10k.fvecs` | 官方 10K query 池（已存在） |
| `data/sift_groundtruth_official.ivecs` | 官方 GT（已存在） |
| `data/sift_gt_official10k_k10.bin` | 官方 GT 转 k=10 内部格式（已存在） |

## 实验计划

| 轮次 | 内容 | 验收 |
|------|------|------|
| R0 | 官方 10K query profiling | 特征 CSV 生成，min_n 分布合理（P50 > 15） |
| R1 | 标签计算 + 与原 POC 对比 | 对比 self-match 污染对标签的影响 |
| R2 | LightGBM 训练 | MAE < 50，模型导出 |
| R3 | C++ 模型导出 | 编译通过，推理 < 0.1μs |
| R4 | Sustained 三方对比 | 256/512MB × 1/4/16T 矩阵完成 |
| R5 | margin 调优 | 最优 margin 确定 |
| R6 | 结论 | promote / 维持 may |
