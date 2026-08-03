# Interfaces — 环境变量

> 条款索引: `API-007`, `API-008`, `API-009`, `API-010`

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
<!-- ndf: kind=req level=tbd layer=L1 status=draft since=0.8 source=deduced topic=io-pipelining -->
<!-- ndf: depends-on=DEC-060,CON-POC-001 -->

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
