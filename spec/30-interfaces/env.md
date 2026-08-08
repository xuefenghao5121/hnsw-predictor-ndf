# Interfaces — 环境变量

> 条款索引: `API-007`, `API-008`, `API-009`, `API-010`, `API-011`, `API-012`, `API-013`

## 实验性环境变量 (DEC-017, DEC-019) {#API-007}
<!-- ndf: kind=req level=should layer=L1 status=stable since=0.2 source=deduced -->

### PAGE_SEARCH (DEC-017)

| 属性 | 值 |
|------|-----|
| 类型 | `int` (0 或 1) |
| 默认值 | `0` (关闭) |
| 取值 | `0`=仅计算候选向量 L2；`1`=扫描 4KB 页内全部向量 |
| 前置条件 | `FINE_RERANK=1` + `VEC_BLOCKS_PATH` 已设置 |
| 副作用 | 增加 `vec_slot_to_node_` 反向映射内存 (~4MB @1M nodes) |
| 对应代码 | `disk_hnsw.cpp:1736` `kPageSearch`, `disk_hnsw.cpp:1757` `pageSearchScan()` |

### DYNAMIC_WIDTH (DEC-019)

| 属性 | 值 |
|------|-----|
| 类型 | `int` (0 或 1) |
| 默认值 | `0` (关闭) |
| 取值 | `0`=固定 efSearch；`1`=自适应衰减 |
| 前置条件 | `TWO_STAGE=1` + PQ 已加载 |
| 适用函数 | `searchLayer0()` (其它变体暂不适用) |

### DW_CONVERGE_HOP

| 属性 | 值 |
|------|-----|
| 类型 | `int` (正整型) |
| 默认值 | `10` |
| 取值范围 | `[5, 100]` (建议) |
| 含义 | 连续 N 跳 top-3 candidate 无变化触发宽度衰减 |

### DW_DECAY

| 属性 | 值 |
|------|-----|
| 类型 | `double` (浮点) |
| 默认值 | `0.75` |
| 取值范围 | `(0, 1.0)` |
| 含义 | 几何衰减因子，`new_ef = max(EF_SEARCH_MIN, current_ef * DW_DECAY)` |

### EF_SEARCH_MIN

| 属性 | 值 |
|------|-----|
| 类型 | `int` (正整型) |
| 默认值 | `32` |
| 取值范围 | `[k, ef_search]` (不低于 k) |
| 含义 | 衰减下限，保证最小候选集大小 |

## 冷 I/O 模式环境变量 {#API-008}
<!-- ndf: kind=req level=should layer=L1 status=stable since=0.3 source=deduced -->
<!-- ndf: depends-on=DEC-021,BEH-016 -->

| 环境变量 | 类型 | 默认值 | 取值范围 | 说明 | 关联条款 |
|----------|------|--------|---------|------|---------|
| `EVICT_PAGE_CACHE` | int | 0 | 0/1 | 1=每次查询后 posix_fadvise(DONTNEED) 驱逐 vecblocks page cache | [[DEC-021]] [[BEH-016]] |

## I/O Pipelining 环境变量 (探索轨) {#API-010}
<!-- ndf: kind=req level=tbd layer=L1 status=deprecated since=0.8 source=deduced topic=io-pipelining -->
<!-- ndf: depends-on=DEC-060,CON-POC-001 deprecated-by=DEC-071 -->

> **track: poc | status: draft | topic: io-pipelining**  
> 装订器: `poc/io-pipelining/ndf/TOPIC.md`；提案 `spec/open/proposal-io-pipelining.md`。  
> 行为契约见 [[BEH-021]] / [[BEH-022]] / [[BEH-023]]（接口不反向 depends-on 行为，避免环）。

| 环境变量 | 类型 | 默认值 | 取值范围 | 说明 | 关联条款 |
|----------|------|--------|---------|------|----------|
| `PIPE_FINE` | int | 0 | 0/1 | 1=Phase A 期间异步预取 Fine Rerank 候选页 (L5 pipe_ring_) | [[BEH-021]] [[DEC-060]] |
| `PIPE_THRESHOLD` | int | （未设置时对齐 `REFINE_EF`） | `[k, REFINE_EF]` | 预取触发的最大 rank，仅预取有望进入 Phase B 的候选 | [[BEH-021]] |
| `PIPE_L1` | int | 0 | 0/1 | 1=开启 L1/L2/L3 CPU cache 向量预取 (_mm_prefetch) | [[BEH-022]] |
| `PIPE_L4` | int | 0 | 0/1 | 1=开启 L4 page cache 旁路填充 (仅 Buffered 模式) | [[BEH-023]] |

> 前置条件: `TWO_STAGE=1` + `FINE_RERANK=1` + `fine_rerank_ok_` 已初始化  
> 内存开销: pipe_ring_ buffer pool ~200×4KB = 800KB (thread_local)  
> 三个开关独立控制，可组合验证各层独立贡献和叠加效果。  
> `PIPE_THRESHOLD`：环境变量未设置时实现 MUST 使用当前 `REFINE_EF`（或等价精排 ef），而非字面字符串。

## Read Coalescing 环境变量 (已废弃) {#API-009}
<!-- ndf: kind=req level=may layer=L1 status=deprecated since=0.6 source=deduced -->
<!-- ndf: depends-on=DEC-060 -->

> **Deprecated (2026-07-31):** 代码已回退，环境变量不再生效。见 [[BEH-017]] 和 [[DEC-061]]。

## Benchmark / 调参环境变量 {#API-011}
<!-- ndf: kind=req level=should layer=L1 status=stable since=0.1 source=observed -->
<!-- ndf: depends-on=CON-002,DEC-073,DEC-086 trunk-ref=c63694fe44762fea06443b78496c546e216d8cd1 -->

> **Trunk**: `trunk-ref=c63694fe44762fea06443b78496c546e216d8cd1`（sustained-param-retuning promote，[[DEC-086]] 追加 sustained 调参推荐；FLAT_VEC 默认 4->64 见 [[DEC-073]]）。
> 下表「Trunk 默认」对齐该 SHA 的 `src/`；「测量常用」供 SLA 正文引用，**不是**代码默认。  
> 性能配置点定义见 [[DEF-024]]。  
> **Sustained 调参推荐**（[[DEC-086]]，2026-08-07）：
> - `FLAT_VEC_MB`: 512MB cgroup 下 agg QPS 最优为 64（sustained），160 为 steady QPS 最优
> - `REFINE_EF`: 256MB cgroup 下 sustained 推荐值为 90（ADAPTIVE 模式, recall 95.56%, +13.6% QPS vs EF=100）
>
> source: poc/sustained-param-retuning/ndf/evidence/r0-r1-ef-adaptive-retuning-20260807.md ; r2-r3-fvc-combo-20260807.md
>
> **Pipeline 调参推荐**（[[DEC-087]]，2026-08-08）：
> - `REFINE_EF`: 256MB sustained **BASE** 模式推荐 65（recall 95.52%, +127% QPS vs EF=100）
> - `M_graph`: 16（Trunk 默认已正确，无需更改）
> - Block size 32K vs 64K: +52.5% QPS（延期验证，需 pipeline 重建）
>
> source: poc/pipeline-param-retuning/ndf/evidence/r0-r4-redo-20260808.md

| 环境变量 | 类型 | Trunk 默认 | 测量常用 | 说明 |
|----------|------|-----------|---------|------|
| `FLAT_VEC_MB` | int (MB) | **64** | 64 / 160 | 热向量 LRU；512MB sustained agg 最优=64, steady 最优=160 ([[DEC-086]])；覆盖见 [[CON-002]] |
| `CACHE_MB` | int (MB) | （benchmark **必填**） | 64 | BlockCache 大小 |
| `FINE_PREAD` | int 0/1 | 0 | 1 | 1=pread 替代 io_uring（多线程推荐） |
| `FINE_BUFFERED` | int 0/1 | 0 | 1 | 1=buffered I/O（含 page cache） |
| `FINE_RERANK` | int 0/1 | 0 | 1 | 1=4KB 页粒度精排 |
| `TWO_STAGE` | int 0/1 | 0 | 1 | 1=PQ 粗筛 + 精排 |
| `NUM_THREADS` | int | 1（未设时） | 4 / 16 | 并发搜索线程数 |
| `REFINE_EF` | int | 200 | 100 | Phase A 粗筛 ef；256MB sustained 推荐 90 ([[DEC-086]]) |

## L4 WILLNEED 环境变量 {#API-012}
<!-- ndf: kind=req level=may layer=L1 status=stable since=0.9 source=observed topic=l4-cache-mgmt -->
<!-- ndf: depends-on=BEH-024,DEC-070 trunk-ref=2f008f7f60229e68416d20f7e4fdba4071604969 -->

> **Trunk**: `trunk-ref=2f008f7f60229e68416d20f7e4fdba4071604969`（feat: promote WILLNEED，[[BEH-024]]）。

| 环境变量 | 类型 | Trunk 默认 | 取值范围 | 说明 | 关联条款 |
|----------|------|-----------|---------|------|----------|
| `L4_WILLNEED` | int | 0 | 0/1 | 1=Fine rerank pread 前对 pages_needed 调用 posix_fadvise(WILLNEED)，启动内核异步 readahead | [[BEH-024]] [[DEC-070]] |

> 前置条件: `FINE_RERANK=1` + `FINE_PREAD=1` + `FINE_BUFFERED=1`  
> 内存开销: 无额外内存（仅 fadvise 系统调用）  
> 适用场景: page cache 严重受限时效果显著（SIFT1M 256MB: 17.7x QPS）  
> 不适用场景: page cache 充裕或 I/O 量主导（512MB: +5.5%; DEEP10M 2GB: ~0%）

## WILLNEED 多线程扩展环境变量 {#API-013}
<!-- ndf: kind=req level=may layer=L1 status=stable since=0.9.5 source=observed topic=multi-thread-scaling -->
<!-- ndf: depends-on=API-012,BEH-027,BEH-028,DEC-074,DEC-075 trunk-ref=162377ee75dbb6a3042572bce47686b92a86aa42 -->

> **Trunk**: `trunk-ref=162377ee75dbb6a3042572bce47686b92a86aa42`（WILLNEED_BG + VL_POOL，[[BEH-027]]）。  
> `PAGE_MERGE_BG` 合入 tip：`edddd232947c5ec5bde27065add3b1a60621cb80`（[[BEH-028]]）。

| 环境变量 | 类型 | Trunk 默认 | 测量常用 | 说明 | 关联 |
|----------|------|-----------|---------|------|------|
| `WILLNEED_BG` | int 0/1 | 0 | 1 | 后台 I/O 线程提交 WILLNEED；前置 `L4_WILLNEED=1` | [[BEH-027]] |
| `VL_POOL_THREADS` | int | 999（不启用） | 14 | `NUM_THREADS >= N` 时复用 thread_local VisitedList | [[BEH-027]] |
| `PAGE_MERGE_BG` | int 0/1 | 0 | 1（仅 256MB 12T+） | BG 线程合并连续页 fadvise；前置 `WILLNEED_BG=1` | [[BEH-028]] |

> `PAGE_MERGE_BG`：**仅** 256MB cgroup 高并发有益；512MB 下有害。MUST NOT 默认开启。

## PQ 距离间隙自适应 EF 环境变量 {#API-017}
<!-- ndf: kind=req level=may layer=L1 status=stable since=0.9.8 source=observed topic=helmsman-adaptive -->
<!-- ndf: depends-on=BEH-004,DEC-086 trunk-ref=c63694fe44762fea06443b78496c546e216d8cd1 -->

| 环境变量 | 类型 | Trunk 默认 | 取值范围 | 说明 | 关联 |
|----------|------|-----------|---------|------|------|
| `ADAPTIVE_EF` | int 0/1 | 0 | 0/1 | 1=启用 PQ 距离间隙自适应 Phase B 候选数 | [[BEH-033]] |
| `ADAPTIVE_EASY_GAP` | float | 1.006 | >1.0 | gap ≥ 此值判为 easy query | [[BEH-033]] |
| `ADAPTIVE_HARD_GAP` | float | 1.002 | >1.0 | gap ≤ 此值判为 hard query | [[BEH-033]] |
| `ADAPTIVE_EASY_EF` | int | 50 | 1-1000 | easy query Phase B 候选上限 | [[BEH-033]] |
| `ADAPTIVE_HARD_EF` | int | 200 | 1-1000 | hard query Phase B 候选上限 | [[BEH-033]] |

> 前置条件: `TWO_STAGE=1` + `FINE_RERANK=1`
> 适用场景: 256MB cgroup 高并发 (≥4T)。SIFT1M 4T/8T 实测 +31% QPS。
> **不推荐** 512MB cgroup（page cache 充裕，收益不明或略退）。
> recall 约束: 启用时 recall ≥ 95%（SIFT1M 校准 95.30%）。
>
> **Sustained 调参推荐**（[[DEC-086]]，2026-08-07）：
> - 256MB sustained: `ADAPTIVE_EASY_EF=40`（recall 95.10%, +12.7% QPS vs eef=50）
> - 需配合 `REFINE_EF=90` 使用
> - 200q 下 eef=40 因 recall < 95% 被否；sustained 下 recall 基线更高 (96.00% vs 95.75%)，达标
>
> source: poc/sustained-param-retuning/ndf/evidence/r0-r1-ef-adaptive-retuning-20260807.md

> **Pipeline 调参补充**（[[DEC-087]]，2026-08-08）：
> - ADAPTIVE 增益与 recall 余量强相关：M=24 EF=60 (余量 1.60pp) +68%，M=16 EF=65 (余量 0.52pp) +3-7%
> - M=16 EF=65 +ADAPTIVE 16T: agg=4,057（最高吞吐）但 recall 仅 95.17%（余量紧）
> - GBDT-v3 重训在 256MB 低 EF 下无效（负结果，见 [[DEC-087]]）
>
> source: poc/pipeline-param-retuning/ndf/evidence/r0-r4-redo-20260808.md

## GBDT 学习式候选数预测环境变量 {#API-018}
<!-- ndf: kind=req level=may layer=L1 status=stable since=0.9.9 source=observed topic=gbdt-learned-pruning -->
<!-- ndf: depends-on=BEH-004,DEC-084 trunk-ref=7f59fae -->

| 环境变量 | 类型 | Trunk 默认 | 取值范围 | 说明 | 关联 |
|----------|------|-----------|---------|------|------|
| `LEARNED_EF` | int 0/1 | 0 | 0/1 | 1=启用 GBDT 预测 Phase B 候选数 | [[BEH-034]] |
| `GBDT_MARGIN` | float | 0.8 | 0.1-2.0 | 预测值缩放系数 (越小越激进) | [[BEH-034]] |

> 前置条件: `TWO_STAGE=1` + `FINE_RERANK=1`
> 与 `ADAPTIVE_EF` 互斥；若同时开启，`LEARNED_EF` 优先。
> 模型: SIFT1M 训练的 100 棵 LightGBM 树，编译期嵌入 C++ if-else 规则表 (186KB)。
> recall 约束: 启用时 recall ≥ 95%（sustained 实测 95.99%）。
>
> ⚠️ **收益状态：当前模型无效**（[[DEC-084]] §5）。原声明“10K query +33~124% QPS”
> 基于被 self-match 污染的 base-sampled query 池；sustained 口径（[[CON-SLA-019]] 禁预热
> + 官方 query 池）实测增益仅 **−0.9~+1.8%**（噪声内）。
> 根因：训练标签取自污染池，模型学到的候选数分布系统性偏低。
> 生产环境 SHOULD 用 `ADAPTIVE_EF`（[[API-017]] / [[BEH-033]]）代替；
> 本旋钮保留供重训后重测。
