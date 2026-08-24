# Proposal: 负结果闭环 — bfs-cluster rejected {#PROP-REJECT-BFS-CLUSTER}

> track: poc
> Status: Implemented on 2026-08-12
> 日期: 2026-08-12
> Subject: bfs-cluster topic 负结果闭环
> 对齐: [[BEH-020]]
> Rejects: bfs-cluster
> 关联: [[BEH-037]], [[DEC-096]], [[DEC-018]]

## 1. 根因

R0（2026-08-10，256MB cgroup，sustained golden，k=1024）证实 BFS-supervised k-means
对 cluster 赋值无实质影响，QPS 略降。

| λ | graph_aligned | QPS vs pure k=1024 | 判定 |
|---|---------------|-------------------|------|
| 1.0 | 0.4–0.5% | ≈ pure k-means | 无分离 |
| 100 | 0.4–0.5% | 1,774 vs 1,812 (−2.1%) | 无收益 |

**根因：** k=1024 下每 cluster 平均每节点仅 ≤2–3 个 graph neighbor；graph penalty
项 λ×N_c 被 centroid 距离（gap ~100–1000）完全淹没。HNSW graph neighbor 本身在向量空间中
刻意保持多样性，graph signal 过于稀疏，无法引导 cluster assignment。

> source: poc/bfs-cluster/NOTES.md ; poc/bfs-cluster/ndf/TOPIC.md
> track: reject ; Topic: bfs-cluster

## 2. 废弃 ID 列表

| ID | 位置 | 当前 status | 动作 |
|----|------|------------|------|
| — | — | — | **无** — 本主题未写入 Trunk draft 条款 |

## 3. 提案状态变更

| 提案 | 动作 |
|------|------|
| _(none)_ | N/A — 无关联 open 提案 |

## 4. Trunk 确认

BFS-supervised k-means 代码从未合入 `src/`。实现仅存在于 `poc/bfs-cluster/`。
Trunk 仍使用 pure k-means（[[BEH-037]] / DEC-096 within-block sort）。无需 revert Trunk。

## 5. 归档

- `poc/bfs-cluster/ndf/` 迁入 `spec/archive/2026-08/poc-bfs-cluster/`
- `poc/bfs-cluster/` 代码保留（供复现参考）

## 6. 后续影响

- bfs-cluster topic 关闭；page-packer 在 `vecblock-layout` 表面上的冲突解除
- 未来若降低 k 或改变 graph 密度假设，MUST 开平级新 topic（[[BEH-025]] 关闭后重启）

## 7. 非目标

- 不删除 POC 代码
- 不改写已推送历史
- 不改 Trunk `src/` 或 stable 条款
