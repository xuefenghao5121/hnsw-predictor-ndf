# Proposal: Promote gbdt-learned-pruning — GBDT 学习式候选数预测

> track: promote
> Status: Implemented on 2026-08-06
> Created: 2026-08-06
> Topic: gbdt-learned-pruning
> Promotes: gbdt-learned-pruning
> Trunk SHA at baseline: 7f59fae
> Related: [[DEC-028]], [[Q-002]], [[BEH-033]], [[BEH-004]]

## 1. 概述

将 POC `gbdt-learned-pruning` 晋升至 Trunk。GBDT 模型利用 Phase A 的 PQ 距离分布
多特征（gap_ratio, d0, d9, d_mean, d_std, d_cv 等）预测 per-query Phase B 最优候选数。

### 核心机制

Phase A 结束后，提取 11 维特征向量 → 100 棵 LightGBM 决策树（C++ if-else 规则表）
→ 预测候选数 × margin → Phase B 候选截断。

### 实测收益（10K query, I/O bound 场景）

| 配置 | vs Baseline |
|------|------------|
| 256MB 4T | **+88.7%** |
| 256MB 16T | **+124.3%** |
| 512MB 4T | **+53.2%** |
| 512MB 16T | **+99.7%** |

### 环境变量

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| LEARNED_EF | 0 (关闭) | 总开关，opt-in |
| GBDT_MARGIN | 0.8 | 预测值缩放系数 |

## 2. 证据摘要

### R0: 10K query profiling
- P50 min_n=21, 68% query 只需 ≤30 候选（vs 固定 100）

### R4-R5: 完整 scaling (10K query)

256MB:
| 线程 | Baseline | GBDT | Δ |
|------|---------|------|---|
| 1T | 1,121 | 1,555 | +38.7% |
| 4T | 2,341 | 4,418 | +88.7% |
| 8T | 2,314 | 4,919 | +112.6% |
| 16T | 2,099 | 4,707 | +124.3% |

512MB:
| 线程 | Baseline | GBDT | Δ |
|------|---------|------|---|
| 4T | 4,129 | 6,324 | +53.2% |
| 16T | 5,583 | 11,149 | +99.7% |

### 200q cache-hit 发现

200q benchmark 的 working set (~10MB) 全进 page cache → 不是 I/O bound → GBDT 无优势。
10K query (~488MB working set) 才是真实 I/O bound 场景。

## 3. Draft → Stable ID 清单

| Draft ID | → Stable ID | 文件 |
|----------|-------------|------|
| BEH-034 | **BEH-034** (stable) | `spec/20-behavior/search.md` |
| API-018 | **API-018** (stable) | `spec/30-interfaces/env.md` |

### DEC 记录

| ID | 说明 |
|----|------|
| **DEC-082** | GBDT vs 启发式效果对比 + I/O bound 场景分析 |
| **DEC-083** | 200q cache-hit 假象发现 |

## 4. 语义核决策 ([[META-004]])

- **不要**。GBDT 模型作为 C++ if-else 规则表嵌入，无运行时模型推理依赖。
  模型文件 (186KB) 编译进二进制，不涉及 spec/models/ 金标。

## 5. 基线/表面影响

### 表面冲突

`explore_surface=search-adaptive` 与 helmsman-adaptive 相交。helmsman-adaptive 已 promoted
（BEH-033 ADAPTIVE_EF）。LEARNED_EF 和 ADAPTIVE_EF 互斥（不会同时启用），不冲突。

## 6. 合入计划

### 源文件

- `src/core/disk_hnsw.cpp`: searchKnn() 中插入 GBDT 预测逻辑（BEH-033 块之后）
- `include/gbdt_model.h`: 新增，186KB GBDT if-else 规则表
- 不含 LLSP profiling 代码（仅 POC 调试用）

### 不改默认行为

- LEARNED_EF 默认 0（关闭）
- ADAPTIVE_EF 默认 0（关闭）
- 两者可共存，但不会同时激活
