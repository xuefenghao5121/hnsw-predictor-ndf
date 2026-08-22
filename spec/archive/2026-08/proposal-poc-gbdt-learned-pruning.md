# Proposal: POC — GBDT 学习式剪枝 (LLSP for DiskHNSW)

> track: poc
> Status: Implemented on 2026-08-06
> Created: 2026-08-06
> Topic: gbdt-learned-pruning
> depends-on-topic: helmsman-adaptive (promoted)
> Related: [[DEC-028]], [[Q-002]], [[BEH-033]], [[BEH-004]]

## 1. 背景

HELMSMAN 用 GBDT 预测 per-query 最优 nprobe，实现 1.1-1.6x 吞吐提升。
我们的 helmsman-adaptive POC 已验证"自适应比固定好"（PQ gap 启发式 +31% QPS），
但启发式只用单一特征（gap_ratio）。

GBDT 可以利用更多特征（PQ 距离分布的多个统计量）预测更精细的策略，
潜在收益超过启发式。

## 2. 探索假设

**H1**: GBDT 模型利用多特征预测 per-query 候选数，比单一 gap_ratio 启发式获得更高 QPS，
同时维持 recall ≥ 95%。

**H2**: GBDT 推理延迟 (<1μs) 占 Fine Rerank 总延迟 (<500μs) 比例 <0.2%，不构成瓶颈。

**H3**: SIFT1M 的 query 难度分布存在足够方差，使学习式剪枝有意义。

## 3. 与 helmsman-adaptive 的关系

| | helmsman-adaptive (promoted) | gbdt-learned-pruning (新) |
|--|-------------------------------|---------------------------|
| 决策依据 | gap_ratio (1 特征) | 多特征 (PQ 距离统计量) |
| 决策粒度 | 3 档 (easy/normal/hard) | 连续值 (回归预测候选数) |
| 模型 | 无 (阈值比较) | LightGBM GBDT |
| 开销 | O(1) | O(<1μs) |
| opt-in | ADAPTIVE_EF=1 | LEARNED_EF=1 (新) |

**不是替代，是增强**。ADAPTIVE_EF 保持可用，GBDT 是更高级的 opt-in。

## 4. 实验计划

### R0: Profiling — 收集训练数据

在 SIFT1M 上为每个 query 收集：
- **特征**: Phase A 的 top-K PQ 距离 (d_0, d_1, ..., d_9)，gap_ratio, 距离 std/mean, 候选数
- **标签**: 满足 recall@10 ≥ 95% 的最小候选数 (brute-force 二分搜索)
- 配置: 256MB 4T (与 helmsman-adaptive 一致)

### R1: 训练 GBDT 模型

- 工具: LightGBM (Python)
- 特征: R0 收集的统计量
- 目标: 回归 (预测最小候选数) 或分类 (候选数档位)
- 树深度: ≤5 (亚微秒推理)
- 训练集/测试集: 80/20 随机划分

### R2: 模型推理集成

- 将 LightGBM 模型导出为 if-else 规则表 (C++ 数组)
- 嵌入 disk_hnsw.cpp: Phase A 结束后查表得到候选数
- 无运行时 Python 依赖

### R3: 性能验证

对比三者在 256MB 4T 下的表现：
- 基线 (REFINE_EF=100 固定)
- 启发式 (ADAPTIVE_EF=1)
- GBDT (LEARNED_EF=1)

### R4: 多线程 scaling

如果 R3 有收益，验证 1T/4T/8T/16T scaling。

### R5: 512MB 回归

验证 512MB 下不退化。

## 5. 晋升条件

- recall ≥ 95%
- 256MB 4T/8T QPS 比 ADAPTIVE_EF 启发式再提升 ≥10%
- 512MB 无退化（opt-in 默认关闭）
- GBDT 推理延迟 <1μs

## 6. 负结果条件

- GBDT 比启发式无显著优势 → reject，记录 DEC（"单一 gap_ratio 已足够"）
- 推理延迟过高 → reject，记录 DEC
- 训练数据不足/标签质量差 → reject 或 defer

## 7. explore_surface

`search-adaptive,learned-pruning,fine-rerank`

## 8. draft 条款预览

| ID (draft) | 类型 | 说明 |
|------------|------|------|
| BEH-034 (draft) | behavior | GBDT 学习式候选数预测 |
| API-018 (draft) | env | LEARNED_EF, MODEL_PATH |
| DEC-082 (draft) | decision | GBDT vs 启发式效果对比决策 |

## 9. 技术约束

- **无运行时 Python 依赖**: 模型必须导出为 C++ 可执行的格式
- **线程安全**: GBDT 推理 (读模型) 天然线程安全 (只读)
- **模型大小**: ≤100KB (规则表或小树)
- **训练数据**: SIFT1M 200 query 足够？（可能需要更多 query — 用 1000 或 10000 query）
