# 提案：分层 Vamana（HNSW 层级 × DiskANN 层内建图）优化 DiskHNSW

> track: poc
> status: reviewed
> plane: product
> control-flow: managed
> proposal-id: hierarchical-vamana-build
> flow-id: hierarchical-vamana-build
> 日期: 2026-08-25
> depends-on: CHR-001, ARCH-001, ARCH-002, CON-SLA-001, VER-001
> 范围: 探索「上层 HNSW 式分层 + 每层 Vamana 建图」是否优于现行 hnswlib 建图流水线；仅 `poc/`；不改 Trunk 默认路径
> explore_surface: hierarchical-vamana, graph-build, diskann, hnsw-layers

Status: Implemented on 2026-08-25
Reviewed: 2026-08-25T07:56:48Z (human phrase `已审核`)

<!-- ndf:gate-slice begin=proposal_contract -->
人类原话：通过网络搜索与论文学习 DiskANN 的 Vamana 磁盘建图方式，结合 HNSW 分层建图，给出分层建图方案（参考 jvector：层级结构借鉴 HNSW，每层内部用 Vamana），以优化 DiskHNSW。

## 1. 背景与对照目标

当前 Trunk（`d0ae5dd`）建图入口为 `src/pipeline/build_index.cpp`：**用 hnswlib 构建完整 HNSW**，再提取图、BFS 重排、分块、PQ。搜索侧已是 DiskHNSW（图/PQ 常驻 + 向量按需 I/O），对照基线见 [[CON-SLA-001]] / `bl-trunk-d0ae5dd`。

优化目标（相对该对照）：在 **≥95% recall（sustained）** 前提下，改善建图质量与/或查询跳数/吞吐/内存，或同等质量下降低建图/驻留成本。数字一律 draft，须按 [[VER-001]] 复测。

## 2. 文献与开源要点（调研摘要）

### 2.1 DiskANN / Vamana（NeurIPS 2019）

- 论文：[DiskANN: Fast Accurate Billion-point Nearest Neighbor Search on a Single Node](https://suhasjs.github.io/files/diskann_neurips19.pdf)
- **Vamana** 为单层有向图：随机初始化出边 → 迭代 **GreedySearch**（从 medoid 贪心找候选）→ **RobustPrune**（`alpha` 控制角多样性，保留长边）→ 可选二遍 `alpha>1` 加强远程连接。
- DiskANN 整系统：图可落盘；常与 PQ 粗距 + SSD 精确距两阶段查询配合。与本仓「图常驻 + 向量 I/O」同族。

### 2.2 HNSW 分层

- 多层「跳表」：上层稀疏快导航，底层密图保召回；插入时按层概率分配，层内邻接受 `M` / `efConstruction` 约束。
- 本仓现状：整图由 hnswlib HNSW 生成，再压成 DiskHNSW 存储布局。

### 2.3 jvector 混合（直接对标）

- 权威表述（[jbellis/jvector README](https://github.com/jbellis/jvector)）：*「borrows the hierarchical structure from HNSW, and uses Vamana (the algorithm behind DiskANN) within each layer.」*
- 实现参数：`addHierarchy=true` 时为 HNSW 式多层；层内 `M`、`beamWidth`、`alpha`、`neighborOverflow` 走 Vamana 剪枝；上层邻接可纯内存，底层可落盘 + 两阶段（PQ/BQ 粗筛 + 磁盘精距）。
- 用户所指 [vbekiaris/jvector](https://github.com/vbekiaris/jvector) 为同系 fork/镜像；设计语义以 jvector 主线 README 为准。

## 3. 假设（POC）

**H0**：在 DiskHNSW 存储/搜索外壳不变（或最小适配）的前提下，用 **「HNSW 层分配 + 每层 Vamana RobustPrune 建边」** 替换「整图 hnswlib HNSW 建边」，可在 sustained 协议下达到对照召回，并以更少无效边或更短导航路径改善 QPS / 内存（具体指标在 TOPIC 中钉死）。

## 4. 方案草案（设计意图，非 stable 契约）

```text
Layer Lmax … L1（稀疏，常驻内存邻接）  — 每层：Vamana(GreedySearch + RobustPrune, α)
Layer L0（密图，CSR / 可与现 L0 布局对齐）— 同上；向量仍按需 I/O + PQ 粗筛
```

| 步骤 | 内容 |
|------|------|
| A | 点集按 HNSW 规则分配最高层（或等价几何抽样） |
| B | 自顶向下 / 增量插入：在目标层及以下做 beam 搜索，候选集经 RobustPrune 写入出边 |
| C | 可选二遍 α>1 强化 L0 长边（对齐 DiskANN 实践） |
| D | 导出邻接 → 现有 extract / BFS reorder / write_blocks / PQ 流水线（尽量复用） |
| E | 搜索：上层纯内存下降 → L0 + 现有 Fine Rerank / BlockCache |

**非目标（本 POC）**：重写整个 DiskANN 分片合并十亿点流水线；改 VER 金标口径；默认打开合入 Trunk。

## 5. 探索表面与隔离

- `explore_surface`: `hierarchical-vamana`, `graph-build`, `diskann`, `hnsw-layers`
- 实现 MUST 落在 `poc/hierarchical-vamana/`（[[BEH-018]]）：改构建逻辑先拷相关 pipeline/头文件进 poc，再改。
- 对照：Trunk `d0ae5dd` + [[CON-SLA-001]] 场景（SIFT1M sustained 512MB/16T）。

## 6. 验收（探索期，draft）

1. 在 poc 内可构建索引并跑通现有搜索路径（或 poc 内最小搜索壳）。
2. `make test` 子集 + sustained（或约定缩小集）相对 `bl-trunk-d0ae5dd` 报告 recall/QPS/内存；**不**写入 stable SLA。
3. NOTES/TOPIC 记录：层数、`M`/`R`、`α`、`beam`、相对对照的 Δ% 与失败模式。

## 7. 草案条款（仅提案内，status=draft）

探索成功后再开 promote 写入 `spec/20-behavior` / `10-architecture`。本提案不铸造稳定 `{#BEH-*}`。

可选草案 ID（装订器用）：

- draft `BEH-HV-001`：构建 MUST 支持分层分配 + 层内 Vamana prune（opt-in）。
- draft `ARCH-HV-001`：上层邻接内存驻留、L0 与现 DiskHNSW 块布局兼容或明确迁移表。

## 8. 下一步（人审后）

「已确认」→ 落提案状态；「已审核」→ 写齐 `poc/hierarchical-vamana/ndf/` 装订器 → 人「派发」实现/测量。
<!-- ndf:gate-slice end=proposal_contract -->

## Control receipts

| event | phrase | actor | at | proposal_sha | flow_id | hop | status |
|-------|--------|-------|----|--------------|---------|-----|--------|
| proposal.confirmed | 已确认 | human | 2026-08-25T07:51:00Z | 2254d5e59f5ad515b2df1333a88f02f48153c0463b92071f14261d0839b4853f | hierarchical-vamana-build | confirm_land | approved |
| proposal.reviewed | 已审核 | human | 2026-08-25T07:56:48Z | 2254d5e59f5ad515b2df1333a88f02f48153c0463b92071f14261d0839b4853f | hierarchical-vamana-build | review | approved |
