# Proposal: Promote helmsman-adaptive — PQ 距离间隙自适应 EF

> track: promote
> topic: helmsman-adaptive
> Status: Implemented on 2026-08-06
> Created: 2026-08-06
> Promotes: helmsman-adaptive
> Trunk SHA at baseline: 589e903

## 1. 概述

将 POC `helmsman-adaptive` 的**层次 A（PQ 距离间隙自适应 EF）**从探索轨晋升至 Trunk。
**层次 B（Fine Rerank 早终止）**在当前 pread 架构下验证无效，**不晋升**，以负结果关闭。

### 核心机制

在 Phase A（PQ 粗筛）结束后，计算 gap_ratio = dist[k] / dist[k-1]，根据 PQ 距离间隙
动态调整 Phase B 候选数：容易 query 减少候选（省 I/O），困难 query 增加候选（保 recall）。

### 最优配置（校准值）

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| ADAPTIVE_EF | 0 (关闭) | 总开关，opt-in |
| ADAPTIVE_EASY_GAP | 1.006 | gap ≥ 此值 → easy |
| ADAPTIVE_HARD_GAP | 1.002 | gap ≤ 此值 → hard |
| ADAPTIVE_EASY_EF | 50 | easy query 候选上限 |
| ADAPTIVE_HARD_EF | 200 | hard query 候选上限 |

## 2. 证据摘要

### R0: SIFT1M PQ gap 分布

| P10 | P25 | P50 | P75 | P90 | Max |
|-----|-----|-----|-----|-----|-----|
| 1.001 | 1.003 | 1.006 | 1.013 | 1.022 | 1.045 |

### R2: SIFT1M 256MB scaling (recall 95.30%, ≥ 95% 约束)

| 线程 | Adaptive QPS | Baseline QPS | Δ |
|------|-------------|-------------|---|
| 1T | 2,669 | 2,623 | +1.8% |
| 4T | 10,971 | 8,356 | **+31.3%** |
| 8T | 19,397 | 14,703 | **+31.9%** |
| 16T | 19,550 | 18,344 | +6.6% |

### R3: 512MB 回归

全配置 recall 95.75% 不变；QPS -0.4% ~ -7.3%（opt-in 默认关闭，可接受）。

### 层次 B（早终止）: REJECTED

| 配置 | Recall | QPS |
|------|--------|-----|
| B only ET=30 | 93.35% | 7,733 (-0.7%) |
| A+B ET=50 | 94.60% | 10,210 (不如 A only) |

根因：pread 路径先批量读完全部页再算距离，早终止只省几 ns 距离计算，不能省 I/O。

## 3. Draft → Stable ID 清单

| Draft ID | → Stable ID | 文件 | 说明 |
|----------|-------------|------|------|
| BEH-033 (draft) | **BEH-033** (stable) | `spec/20-behavior/search.md` | PQ 距离间隙自适应 EF 行为 |
| API-017 (draft) | **API-017** (stable) | `spec/30-interfaces/env.md` | ADAPTIVE_EF + 阈值环境变量 |

### 不新增 CON-SLA

ADAPTIVE_EF 默认关闭，不影响现有 SLA。256MB 高并发场景的 QPS 提升为 opt-in 增益，
不作为新 stable SLA must（避免将可选行为写入 must SLA）。

### DEC 记录

| ID | 文件 | 说明 |
|----|------|------|
| **DEC-080** | `spec/decisions/16-helmsman-adaptive-promote.md` | SIFT1M gap 校准 + recall/QPS 权衡 |
| **DEC-081** | `spec/decisions/17-fine-rerank-early-termination-reject.md` | 层次 B 负结果决策 |

## 4. 语义核决策 ([[META-004]])

- **是否蒸馏 L3 语义核？** **不要**
- **理由**：纯运行时启发式（O(1) 除法 + 比较），无模型/无训练/无离线分析，不涉及语义核
  或学习式剪枝。不需要 `spec/models/` 金标。
- **缺 `model=` 是否构成 graphcheck 失败？** 否

## 5. 基线/表面影响 (§4c/§4d)

### 受影响 exploring 主题

当前无活跃 exploring 主题与 `explore_surface=search-adaptive` 相交。
（fine-rerank-iouring 已 rejected/closed，l4-cache-mgmt 已 closed）

### 表面冲突

无。ADAPTIVE_EF 是 Phase A→B 之间的候选数控制，不影响 Phase A 图搜索行为
（BEH-024）、L4 cache 管理（BEH-027/028）或 WILLNEED BG 线程（BEH-027）。

## 6. 合入计划

### 源文件

POC 补丁 → Trunk `src/core/disk_hnsw.cpp`：
- searchKnn() 中 Phase A 结束后插入 gap_ratio 计算 + adaptive_limit 分支
- pread 路径和 io_uring 路径的候选循环改为 `adaptive_limit` 上限
- 不含层次 B（早终止）代码

### 不改默认行为

- ADAPTIVE_EF 默认 0（关闭）
- 所有现有 SLA 配置（REFINE_EF=100, FLAT_VEC_MB, WILLNEED_BG 等）不变

## 7. Promote 后检查

1. `ndf_close.py plan` 已执行（见下方）
2. `ndf_index.py index` + `ndf_graphcheck.py`
3. 编译验证
4. 性能验证（现有 SLA 全部合规 + adaptive opt-in 验证）
5. TOPIC.md status → promoted (partial: 层次 A promoted, 层次 B rejected)
6. NOTES.md 头 status 同步
