# DESIGN.md — cluster-gbdt POC Design

> topic_id: cluster-gbdt
> status: draft
> created: 2026-08-13
> links: TOPIC.md hypothesis, BEH-034 (GBDT learned pruning, stable), BEH-037 (cluster-sorted vecblock layout, stable)
> baseline_trunk_sha: 1f684c7
> baseline_status: current
> explore_surface: spec/20-behavior/learned-pruning

**非 SoT**；本文件写 HOW，条款写 WHAT。探索期产物，MUST NOT 作为 Trunk stable 实现依据。

<!-- ndf:gate-slice begin=design_contract -->
## Goals / non-goals

### Goals
- 验证假设：cluster purity 特征是否为 GBDT 候选数预测提供增量信号（超出 11 维距离特征）
- 如有增量：量化 cluster-GBDT vs standard GBDT 在 QPS / recall 上的差异
- 方法：node_id → cluster_id 查找 + cluster 熵/纯度特征 → 12-feature GBDT retrain

### Non-goals
- 不改 Trunk `src/` / `include/` / `tests/`（BEH-018 §6 写入隔离）
- 不改 GBDT 模型架构（LightGBM, 100 棵, max_depth=4）——只加特征
- 不改 cluster assignment 算法（k-means k=1024 已由 vecblock-cluster-reorder 产出）
- 不探索 non-GBDT 方法（如 NN-based predictor）

## Modules and layout

```text
poc/cluster-gbdt/
  train_cluster_gbdt.py        # R0: 12-feature GBDT 训练脚本
  analyze_cluster_purity.py    # R0: cluster purity ↔ recall 相关性分析
  cluster_assignments_100k.npy # k-means assignments (node_id → cluster_id)
  NOTES.md                     # R0 结果记录
  ndf/
    TOPIC.md                   # 主题装订器
    PERF_BASELINE.md           # 性能基线绑定
    DESIGN.md                  # 本文件
    GATES.md                   # 门禁回执
```

## Data / control flow

```text
k-means assignments (cluster_assignments_100k.npy)
        │
        ▼
┌──────────────────────────┐
│ analyze_cluster_purity   │──→ purity / recall correlation report
│ (offline analysis)       │
└──────────────────────────┘
        │
        ▼
┌──────────────────────────┐
│ train_cluster_gbdt       │──→ cluster_gbdt_model.h (12-feature)
│ (LightGBM retrain)       │    Feature importance output
└──────────────────────────┘
        │
        ▼
┌──────────────────────────┐
│ A/B benchmark            │──→ QPS / recall comparison
│ standard GBDT (11 feat)  │    vs PERF_BASELINE
│ vs cluster GBDT (12 feat)│
└──────────────────────────┘
```

**Feature pipeline:**
1. 现有 11 维距离特征 (BEH-034): `[n_coarse, d0, d9, dk, dk1, gap, mean, std, cv, r01, r09]`
2. 新增第 12 维: `cluster_purity = unique_clusters_in_top200 / 200`
3. 训练目标不变: 回归预测最优 fine rerank 候选数

## Trunk boundary

### Copy-then-edit (topic 内修改面)
- 无。本 POC 不修改任何 Trunk `.h` / `.cpp` 文件。
- `cluster_gbdt_model.h` 生成在 `poc/cluster-gbdt/` 内，不写入 `include/`。

### Read-only link (只读链 Trunk)
- `include/gbdt_model.h` — 现有 11-feature GBDT 模型（Trunk stable, BEH-034）
- `include/disk_hnsw.h` — FineRerank / search pipeline 结构参考
- `src/core/disk_hnsw.cpp` — 搜索流程参考（只读）
- BEH-034 (search.md) — GBDT 学习式候选数预测 stable 条款
- BEH-037 (cluster-vecblock-layout.md) — cluster-sorted vecblock layout stable 条款

### MUST NOT write
- `src/**`, `include/**`, `tests/**` (BEH-018 §6)

## Implementation slice

### R1 candidate（当前待决策）

R0 只证伪了旧 Trunk / k=1024 下的单一 purity 特征，不自动证伪在已优化 cluster layout
前提下的 entropy 或 per-cluster signal。当前 baseline 已 stale，MUST 先重测现行 Trunk
R0；在新 R0 前不得把潜在价值表述为正结果，也不得自动选择 reject/close。

- 尝试更细粒度 cluster (k=4096, k=8192)
- 尝试 cluster entropy 替代 purity
- 尝试 per-cluster GBDT（分簇模型）

## Failure modes

| 失败模式 | 行为 | 回退 |
|----------|------|------|
| cluster_purity 无增量信号 | R0 已验证 ❌ | 关闭方向，记录负结果 DEC |
| GBDT overfitting (12 feat, 100 trees) | 训练 RMSE 低但测试无改善 | 减树 / 加正则 |
| cluster assignment 不稳定 | 不同 k 值结果不可复现 | 固定 random seed, 记录 k |
| 推理开销 > 剪枝收益 | QPS 下降 | 不部署，仅记录特征重要性 |

## Verification hooks

- **Measure entry**: `PERF_BASELINE.md` → Config C (M=24, EF=60), SIFT1M
- **Baseline binding**: `bl-trunk-golden-7ee4ee2`（Numbers 见 PERF mutable 区）
- **A/B protocol**: standard GBDT vs cluster-GBDT @1T 256MB cgroup, identical config
- **Evidence**: 结果记录在 `NOTES.md`；如有后续 round，写 `ndf/DELTA.md`
- **不抄 SLA 观测数字**；PERF_BASELINE 是探索观测线，不是合约下限
<!-- ndf:gate-slice end=design_contract -->

## Design evidence history (mutable)

### R0 (2026-08-10)

- `train_cluster_gbdt.py` — 12-feature GBDT 训练 + C header 生成
- `analyze_cluster_purity.py` — cluster purity vs recall 相关性分析
- 结果记录在 `NOTES.md`

| Config | Default QPS | LEARNED_EF QPS | Δ |
|--------|:---:|:---:|:---:|
| BFS baseline | 1,442 | 1,456 | +1.0% |
| Cluster k=1024 | 1,812 | 1,800 | −0.7% |

结论：旧 Trunk 下 cluster purity 无增量信号；该历史结果不自动关闭 R1 candidate。

## References

- [[BEH-034]] spec/20-behavior/search.md — GBDT 学习式候选数预测 (stable, promoted)
- [[BEH-037]] spec/20-behavior/cluster-vecblock-layout.md — Cluster-sorted vecblock layout (stable, promoted)
- [[BEH-018]] spec/meta/process.md — 探索期 NDF 纪律 (写入隔离)
- [[META-010]] spec/meta/process.md — 人工门禁回执
- [[META-007]] spec/meta/process.md — POC 性能线唯一绑定
- Prior topic: `poc/gbdt-learned-pruning/` (promoted, BEH-034 source)
- Prior topic: `poc/vecblock-cluster-reorder/` (promoted, BEH-037 source)
