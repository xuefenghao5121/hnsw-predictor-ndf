# Interfaces — 环境变量

> 条款索引: `API-007`, `API-008`

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
