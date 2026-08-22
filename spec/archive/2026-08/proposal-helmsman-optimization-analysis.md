# Proposal: HELMSMAN 论文可参考优化点分析

> track: open (探索方向提案)
> 日期: 2026-08-06
> 来源: spec/refs/helmsman-osdi26.md (OSDI 2026)
> 关联: [[DEC-026]]、[[DEC-027]]、[[DEC-028]]、[[DEC-029]]、[[Q-002]]、[[BEH-024]]、[[BEH-027]]、[[BEH-028]]
> 状态: 待讨论

## 1. 背景与动机

l4-cache-mgmt POC 已关闭（Pareto 前沿），SIFT1M 的 I/O 优化空间已近极限。
当前项目需要寻找新的优化方向。重新审视 HELMSMAN 论文，对照当前稳态数据，
识别可落地的优化点。

### 当前稳态

| 数据集 | 配置 | QPS | Recall | 瓶颈分布 |
|--------|------|-----|--------|----------|
| SIFT1M 512MB 16T | WILLNEED_BG+POOL+MERGE | 30,332 | 95.75% | I/O 已优化 (refault=725) |
| SIFT1M 256MB 16T | 同上 | 18,675 | 95.80% | I/O 已优化 (refault=725) |
| DEEP10M 2GB 12T | 标准配置 | 2,340 | 95.15% | PQ 计算 80%, I/O 7%, 图 13% |

## 2. HELMSMAN 可参考点分析

### 2.1 学习式剪枝 (LLSP) → 自适应 Fine Rerank ★★★ 最高优先

**HELMSMAN 做法**: GBDT 预测 per-query 最优 nprobe，1.1-1.6x 吞吐提升，>80% query 达标（固定参数仅 40%）。

**我们的现状**: 所有 query 用固定 REFINE_EF=100。不同 query 难度不同:
- 容易的 query: PQ 粗筛 top-K 距离差距大，EF=50 即可收敛，EF=100 浪费 I/O
- 困难的 query: 需要更多候选才能维持 recall

**可参考优化 (3 个层次)**:

#### 层次 A: PQ 距离间隙启发式 (无需模型, 可立即实现)

```
gap = pq_dist[k] - pq_dist[k+1]  // top-K 与 K+1 的距离差
if gap > threshold_easy:  REFINE_EF = 50   // 容易 query, 减半 I/O
elif gap < threshold_hard: REFINE_EF = 200  // 困难 query, 增加候选
else: REFINE_EF = 100                        // 默认
```

- **预期收益**: 平均 EF 从 100 降到 ~70, QPS +15-25%
- **风险**: 阈值需校准, 可能影响边缘 recall
- **验证**: SIFT1M + DEEP10M, 对比 fixed EF=100 vs adaptive
- **实现**: 在 searchKnn 中, Phase A (PQ 粗筛) 后计算 gap, 决定 Phase B 的 EF

#### 层次 B: Fine Rerank 早终止 (无需模型, 可立即实现)

```
// Fine Rerank 过程中, 已处理 N 个候选后:
if (top_k_stable_count > STABLE_THRESHOLD):
    // 连续 M 个候选未改善 top-K, 提前终止
    break;
```

- **预期收益**: Fine Rerank I/O 减少 20-40% (容易 query 更早收敛)
- **风险**: 困难 query 可能过早终止, 需要保守阈值
- **实现**: 在 Fine Rerank 循环中跟踪 top-K 改善次数

#### 层次 C: GBDT 学习式剪枝 (需 profiling 数据, P2.5)

- 对应 [[DEC-028]] / [[Q-002]], 保持原有计划
- 特征: PQ 距离分布 (min/median/max/std), query PCA 分量, top-k gap
- 预测: per-query 的 (refine_ef, enable_fine_rerank)
- 模型: LightGBM, 树深 ≤5, 推理 <1μs
- 前置: 需收集 per-query profiling 数据

**建议**: 先实现层次 A+B (启发式, 无需模型), 验证收益后再决定是否上 GBDT。

### 2.2 批量 I/O 模式 → Fine Rerank I/O 重排 ★★ 中优先

**HELMSMAN 做法**: 聚类 ANNS 的 cluster 读操作相互独立，可批量提交利用 SSD 带宽。

**我们的现状**: Fine Rerank 的候选向量读取已通过 WILLNEED_BG 实现异步预取。但
预取页收集是无序的，fadvise 调用顺序可能与实际访问顺序不一致。

**可参考优化**:

- **WILLNEED 排序优化**: 按 page 号排序后再提交 fadvise，利用内核 readahead 的顺序检测
- **当前 PAGE_MERGE_BG=1** 已部分实现（合并连续页），但未按访问顺序排序
- **进一步**: 按 BFS 层级排序候选 ID，使 Fine Rerank 的 I/O 模式更接近顺序读

**预期收益**: 256MB 下 +5-10% QPS (减少随机 I/O -> 顺序 I/O)
**风险**: 排序开销可能抵消收益 (D5 perf 显示无单一瓶颈 >10%)
**评估**: 收益有限, 可能不值得实现

### 2.3 用户态 I/O (SPDK) → P3 保留 ★ 低优先

**HELMSMAN 做法**: SPDK 达 85% SSD 带宽 (内核 io_uring 仅 26-59%)。

**我们的现状**: 已有 DEC-027/DEC-030 评估, P3 (100M) 保留。
当前 majfault ≈ 5K (SIFT1M) / 68K (DEEP10M) 均为冷缺失, SPDK 无法消除。

**结论**: 维持 DEC-027 决策, P3 再评估。当前无动作。

### 2.4 成本效率指标 → QPS/$ 评估 ★ 低优先

**HELMSMAN 做法**: 250 QPS/$ (vs 内存 HNSW 51 QPS/$)。

**我们的现状**: 使用 QPS/MB (内存效率), 已超越 hnswlib (1.10-1.23x)。

**可参考**: 增加 QPS/$ 维度用于 P3 成本评估, 但不影响当前技术路线。

### 2.5 GPU 加速构建 → 不适用

**HELMSMAN 做法**: GPU 构建 10B 索引 4-7 小时。

**我们的现状**: 单机 CPU 构建, 1M-10M 规模构建时间可接受。不适用。

## 3. 优先级排序

| # | 优化点 | 优先级 | 预期收益 | 实现复杂度 | 数据集 |
|---|--------|--------|----------|-----------|--------|
| 1 | PQ 距离间隙自适应 EF (层次 A) | 🔴 高 | +15-25% QPS | 低 (20 行代码) | SIFT1M + DEEP10M |
| 2 | Fine Rerank 早终止 (层次 B) | 🔴 高 | -20-40% I/O | 低 (30 行代码) | SIFT1M + DEEP10M |
| 3 | GBDT 学习式剪枝 (层次 C) | 🟡 中 | +30-60% QPS | 高 (模型+训练) | P2.5 |
| 4 | WILLNEED 排序优化 | 🟡 中 | +5-10% QPS | 低 | SIFT1M 256MB |
| 5 | SPDK 评估 | ⚪ 低 | 带宽提升 | 高 | P3 |
| 6 | QPS/$ 指标 | ⚪ 低 | 评估维度 | 低 | P3 |

## 4. 建议执行计划

### 阶段 1: 启发式自适应 (可立即开始, 不需要新 POC track)

1. **实现 PQ 距离间隙启发式** (层次 A)
   - 在 searchKnn Phase A 后计算 gap = dist[k] - dist[k+1]
   - 三档: easy (EF=50) / normal (EF=100) / hard (EF=200)
   - 环境变量: `ADAPTIVE_EF=1` (opt-in)
   - 阈值: 需通过 profiling 校准 (建议先跑 200 query 统计 gap 分布)

2. **实现 Fine Rerank 早终止** (层次 B)
   - 跟踪连续无改善候选数
   - 阈值: STABLE_LIMIT=20 (连续 20 个候选无 top-K 改善则终止)
   - 环境变量: `EARLY_TERMINATE=1` (opt-in)

3. **验证**: SIFT1M (512MB+256MB) + DEEP10M (2GB), 对比 fixed vs adaptive

### 阶段 2: GBDT 学习式剪枝 (P2.5, 依赖 profiling)

1. 收集 per-query profiling: gap, dist 分布, I/O 量, recall, 延迟
2. 训练 LightGBM 模型
3. 对比启发式 vs GBDT

### 阶段 3: P3 评估

- SPDK / 聚类范式 / QPS/$ 评估 (100M 规模)

## 5. 不做的事

- 不改 Trunk `src/` (先在 POC 验证)
- 不引入聚类范式 (DEC-026 确认 P2 仍用图方法)
- 不引入 SPDK (DEC-027 确认 P3 再评估)
- 不改 WILLNEED_BG 架构 (L4 POC 已关闭, Pareto 前沿)

## 6. 与现有条款的关系

| 现有条款 | 关系 |
|----------|------|
| [[DEC-028]] | 层次 C 直接对应, 层次 A+B 是简化版前置 |
| [[Q-002]] | 阶段 2 回答此问题 |
| [[DEC-029]] | DEEP10M 瓶颈分析 (PQ 80%) 是自适应 EF 的动机 |
| [[BEH-024]] | L4 已关闭, 自适应 EF 是 L4 之后的下一优化方向 |
| [[BEH-027]] | WILLNEED_BG 不变, 自适应 EF 减少需要 WILLNEED 的页数 |
