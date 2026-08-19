# DESIGN.md — software design (POC binder)

> topic_id: hotspot-optimization
> status: draft
> links: `poc/hotspot-optimization/ndf/TOPIC.md`（Active Hypothesis H1–H4）；`spec/open/proposal-poc-hotspot-optimization.md`（root, Implemented on 2026-08-18）

复制自 `spec/meta/templates/poc/DESIGN.md.stub`。开题实现前 MUST 存在（[[BEH-025]]）。
**非 SoT**；与 `proposals/` draft L1 分工：本文件写 HOW，条款写 WHAT。

<!-- ndf:gate-slice begin=design_contract -->
## Goals / non-goals

### Goals

- **H1 / D1（本轮主切片，推荐优先）**：把 `DiskHNSW::pqDistance` 的 Phase A 距离查表
  （`src/core/disk_hnsw.cpp:298`，M=32 次标量 `t[m*ksub + code[m]]` gather+add）
  改为 SIMD 批量 gather + 归约（FastScan / QuickerADC 式）。
  **约束：距离数值与现状逐位一致（或误差 < 1e-6 且 recall 不变）→ Recall@10 严格不变。**
- 后续可选切片（人工按可行性挑选，非本轮并行）：
  - **H2 / D2**：RaBitQ 1-bit 量化替代 PQ。MUST 先验证随机旋转与 HNSW 图兼容（[[DEC-072]] 前车之鉴）。
  - **H3 / D3**：VisitedList 池化 + `NUM_THREADS≥8` 时自适应禁用 WILLNEED（低复杂度、收益低-中）。
  - **H4 / D4**：候选数再压缩 — 不推荐（[[DEC-072]] 已证 recall≥95% 近天花板）。

### Non-goals

- **不新增任何 Trunk must / DEC / SLA**；不写 `spec/20-behavior/`、`spec/meta/`。
- **不改 [[CHR-006]] Recall@10 ≥ 95% 门槛**。
- 本轮不写 `INTERFACE.md`、`PERF_BASELINE.md`、`DELTA.md`、`GATES.md`，不写 POC 代码。
- 网上论文数字（QuickerADC / RaBitQ 加速比）是**外部观测，不是本仓观测**，不得写成
  must SLA 或本仓收益声明。

## Modules and layout

相对 `poc/hotspot-optimization/` 的模块与文件落点：

```text
poc/hotspot-optimization/
  ndf/DESIGN.md              # this file
  ndf/TOPIC.md               # 已存在（[[BEH-025]] 装订器）
  ndf/proposals/             # stub → spec/open/（已存在）
  ndf/GATES.md               # 已存在（append-only 门禁回执）
  ndf/COMMITS.md             # 已存在
  src/                       # copy-then-edit 工作副本（实现期才建，本轮不建）
    disk_hnsw.cpp            #   ← 拷贝自 src/core/disk_hnsw.cpp，仅改 pqDistance
    disk_hnsw.h              #   ← 拷贝自 include/disk_hnsw.h
    simd.h / simd_x86.h / simd_arm.h / simd_scalar.h  # ← 拷贝自 include/
  ndf/evidence/              # validation 记录（实现期）
  ndf/PERF_BASELINE.md       # 金标绑定（DESIGN已审核 + 实现前 MUST，本轮不写）
```

## Data / control flow

关键路径（Phase A 距离计算）：

```text
query float[128]
   │  buildPqDistTable (SIMD: pqBuildTable_dsub4, AVX2/NEON) —— 已存在
   ▼
pq_dist_table_ float[M × ksub]  (M=32, ksub=256 → 32KB, thread_local)
   │  pqDistance(node):  code = pq_codes_[node*M .. node*M+M)
   ▼
现状:  M=32 次标量 gather  t[m*ksub + code[m]]  →  s0..s3 四路累加   ← 热点 (37.9% @4T)
   │
D1 目标:  8/16 路 SIMD gather (AVX2 _mm256_i32gather_ps) + 水平归约，一次处理 8 个 m
   ▼
float dist (L2 近似) → Phase A 候选排序 → Phase B fine rerank（不在此切片）
```

D1 改造要点（HOW，不含本轮代码）：

1. 将 `code[m]`（uint8）零扩展到 32 位索引：`_mm256_cvtepu8_epi32`。
2. 加常量基址偏移 `[0·ksub, 1·ksub, …, 7·ksub]` 得 8 个绝对索引。
3. `_mm256_i32gather_ps(pq_dist_table_, vindex, 4)` 一次 gather 8 个 float。
4. 水平归约累加；M=32 → 4 次 8-wide gather（或 2 次 16-wide，AVX-512 时）。
5. 数值等价性以「与标量路径逐位一致或 ≤1e-6 且 Recall@10 不变」为验收硬门槛。

## Trunk boundary

- **Copy-then-edit**（实现期才执行，本轮仅声明）：
  - `src/core/disk_hnsw.cpp` → `poc/hotspot-optimization/src/disk_hnsw.cpp`
  - `include/disk_hnsw.h` → `poc/hotspot-optimization/src/disk_hnsw.h`
  - `include/simd.h` + `include/simd_x86.h` + `include/simd_arm.h` + `include/simd_scalar.h`
    → `poc/hotspot-optimization/src/`
- **Read-only link**：`poc/multi-thread-scaling/ndf/evidence/bottleneck-profiling-20260805.md`
  （瓶颈画像 SoT）、`spec/decisions/` 中 [[DEC-072]]（OPQ 不兼容教训）。
- **MUST NOT write Trunk `src/` / `include/` / `tests/`**（[[BEH-018]] 写入隔离）。
  实现仅在收到「可以开始实现」后委派 `poc/hotspot-optimization/src/`。

## Implementation slice

本轮实现空间切片（D1 主切片；其余为后续可选）：

| 切片 | 改动文件（topic 内） | 不改的面 | INTERFACE 符号 | DELTA Feature |
|------|---------------------|---------|---------------|---------------|
| D1 | `src/disk_hnsw.cpp` 的 `pqDistance` 查表循环 | 距离表构建、图遍历、Phase B | `DiskHNSW::pqDistance` | F1 (SIMD-gather lookup) |
| D2 | 量化码生成 + 距离核（独立切片） | HNSW 图结构 | 待定 | F2 (RaBitQ) |
| D3 | VisitedList 管理 + WILLNEED 开关 | 距离计算 | 待定 | F3 (池化/自适应) |

- 实现计划是**非 SoT**；探索期仍适用 [[BEH-018]] 写入隔离。
- D1 不触碰 `buildPqDistTable`（已 SIMD 化）、不触碰图遍历、不触碰 fine rerank。

## Failure modes

- **D1 距离数值漂移**：若 SIMD gather 归约顺序导致浮点累加顺序改变 → 距离轻微不同 →
  候选排序微变 → 潜在 recall 波动。**回退**：保持与标量一致的归约顺序，或以「Recall@10
  严格不变 + 距离 ≤1e-6」为门槛，否则放弃该归约顺序。
- **AVX2 gather 在 ksub=256 下的吞吐未达预期**（gather 指令微码开销）：
  回退到「4 路标量展开 + 软件流水」，或改用 `_mm_shuffle_epi8`（仅 ksub≤16 时可行，
  需缩小子量化器，跨切片依赖）。
- **H2 旋转与图不兼容**（预期风险）：RaBitQ 随机旋转改变邻居排序 → 图遍历走错。
  门禁：R0 只做 recall≥95% 可行性判定，失败即按 [[DEC-072]] 关闭该切片，不污染 D1。
- **本主题所有测量**若沿用 cache-warmed 口径会重蹈 [[DEC-084]] 假象 → 一律以
  sustained 口径为准（见 Verification hooks）。

## Verification hooks

- 测量口径绑定：[[CON-SLA-014]] 严格 cgroup 隔离 + [[CON-SLA-019]] 禁预热 +
  [[CON-SLA-020]] sustained 基线；**不在此抄 SLA 观测数字**。
- R0 基线：`poc/hotspot-optimization/ndf/PERF_BASELINE.md`（金标绑定，实现前 MUST）。
- D1 验收钩子：`pqDistance` SIMD vs 标量 的距离逐位对比 + Recall@10 不变（SIFT1M, 512MB/256MB）。
- 证据落点：`poc/hotspot-optimization/ndf/evidence/`。
- 相对对比若非 Honest/O_DIRECT，MUST 在 NOTES 标明协议（同 [[DEC-063]]）。
<!-- ndf:gate-slice end=design_contract -->
