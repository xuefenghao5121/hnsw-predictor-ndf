# Proposal: 负结果闭环 — cluster-gbdt rejected {#PROP-REJECT-CLUSTER-GBDT}

> track: poc
> Status: Implemented on 2026-08-15
> Confirmed: 已确认
> reviewed: 已审核
> 日期: 2026-08-14
> Subject: cluster-gbdt topic 负结果关闭
> 对齐: [[BEH-020]]
> Rejects: cluster-gbdt
> 关联: [[BEH-034]], [[BEH-037]], [[CON-SLA-020]]

## 1. 根因

Human 判定（2026-08-14，verbatim）: A1 已证伪（entropy 饱和、无聚集）。A2/A3 门在
A1 增量趋势，未满足。走负结果关闭，不要再开 A2/A3 或 PQ simulation。

**A1 证伪证据** — R1 entropy analysis（2026-08-14，Trunk a143392，k=1024 assignments，
groundtruth top-100）:

| 指标 | 值 | 判定 |
|------|-----|------|
| cluster entropy | 0.9945 | **饱和** — 接近 log(94)≈4.54/4.64 上限，分布近乎均匀 |
| purity | 0.063 | 无纯度聚集 |
| dominant_frac | 0.024 | 最大单 cluster 占比 2.4%，无主导 cluster |
| top-100 cluster span | ~94 / 1024 | top candidates 分散在 ~94 个 cluster，**无聚集** |

**根因:** HNSW top-100 候选在 cluster layout（BEH-037, k=1024）上近乎均匀分布
（entropy 饱和 0.9945，top-100 横跨 ~94/1024 clusters），cluster entropy / purity /
dominant_frac 均无法提供旧 purity 特征之外的增量信号。A1（cluster entropy 取代单一
purity）被 R1 数据直接证伪。

**A2/A3 门控失败:** DELTA amendment candidates 中 A2（k=4096/8192 更细粒度 signal）
前置条件为「A1 有增量趋势」，A3（per-cluster predictor）前置条件为「A1/A2 显示跨
cluster 异质性」。A1 证伪 → 两个前置条件均未满足 → A2/A3 保持 deferred，不启动。
PQ coarse simulation 同理由 Human 明令不启动。

> source: poc/cluster-gbdt/ndf/evidence/r1-entropy-analysis-20260814.md ; poc/cluster-gbdt/ndf/DELTA.md ; poc/cluster-gbdt/ndf/COMMITS.md
> track: reject ; Topic: cluster-gbdt

## 2. 废弃 ID 列表

| ID | 位置 | 当前 status | 动作 |
|----|------|------------|------|
| — | — | — | **无** — 本主题未写入 Trunk draft 条款（ledger 仅引用既有 [[BEH-034]]/[[BEH-037]]/[[CON-SLA-020]]） |

## 3. 提案状态变更

| 提案 | 动作 |
|------|------|
| _(none)_ | N/A — 无关联 open 提案 |

## 4. Trunk 确认

cluster-gbdt 全部代码（`train_cluster_gbdt.py`, `r1_entropy_analysis.py`,
`analyze_cluster_purity.py`, `r1_pq_coarse_analysis.py`）仅存在于 `poc/cluster-gbdt/`，
从未合入 `src/`。`src/pipeline/cluster_reorder.cpp` 属 [[BEH-037]]（自
vecblock-cluster-reorder topic promote），与本主题无关。无需 revert Trunk。

## 5. 归档

- 提案「已确认」后：`poc/cluster-gbdt/ndf/` 迁入 `spec/archive/2026-08/poc-cluster-gbdt/`
- `poc/cluster-gbdt/` 代码保留（供复现参考）

## 6. 后续影响

- cluster-gbdt topic 关闭（负结果）；[[BEH-034]] GBDT 学习式候选数预测维持现状（12-feature，
  cluster purity 特征已证无增量）
- 未来若改变 k 粒度假设（k=4096/8192）或 graph 密度前提，MUST 开平级新 topic 重新立项，
  不得在本 topic 内重启 A2/A3
- PQ coarse simulation 方向留给独立 topic 立项决策

## 7. 非目标

- 不删除 POC 代码
- 不改写已推送历史
- 不改 Trunk `src/` 或 stable 条款
- 不写 DEC（本提案为 POC track 负结果闭环，非 DEC 载体）
