# DiskHNSW — Interfaces

> scope: product (30-interfaces)
> status: stable | perf: not-established | bootstrap: adopt
> Observed Trunk SHA: `d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755`

本文件记录 observed Trunk 的公开 API 面与运行时旋钮接口。

## DiskHNSW 公共接口 {#API-001}
<!-- ndf: kind=def level=must layer=L1 status=stable since=0.1 source=observed -->

`include/disk_hnsw.h` 声明检索器主类 `DiskHNSW`，公开面（source=observed）：

- 构造：`DiskHNSW(graph_path, bfs_path, blocks_path, route_path, cache_slots, dim)`
  与可插拔变体 `DiskHNSW(graph_path, bfs_path, unique_ptr<BlockCache>)`。
- 检索：`searchKnn(query, k)`、`batchSearch(...)`、`batchSearchEventDriven(...)`、
  `batchSearchConcurrent(...)`。
- 参数：`setEf/getEf`。
- PQ：`loadPQCodes`、`isPQEnabled`、`getPQParams`、`pqDistance`、`buildPqDistTable`。
- 图信息：`getNumNodes/getDim/getMaxLevel/getEntryPoint`。
- ID 映射：`oldToNew/newToOld`。
- 预取与统计：`enableGraphPrefetch/disableGraphPrefetch`、`getCacheStats`、
  `getGraphPrefetchStats`、`dropPageCache`、`prefetchRecentBlocks`。
- 结构：`PQParams`、`VisitedList`、`QueryState`。

## BlockCache 公共接口 {#API-002}
<!-- ndf: kind=def level=must layer=L1 status=stable since=0.1 source=observed -->

`include/block_cache.h` 声明块缓存 `BlockCache` 与 `IOConfig`、`CachedBlock`、
`CachedNode`、`Stats`。关键方法：`getNodeVector/getNodeNeighbors`、
`getBlockByNodeId/getBlockById`、`prefetchBlock/isInCache/filterNotInCache/tryPrefetch`、
`insertBlock/insertBlocksBatch`、`getFlatVector/putFlatVector/prefetchFlatSlot`、
`getBlockId/getNumBlocks/getNumNodes`、`getStats/hitRate/resetStats`、`dropPageCache`、
`setTraceCallback/getRecentBlockAccesses`。

## 布局编排器 {#API-003}
<!-- ndf: kind=def level=must layer=L1 status=stable since=0.1 source=observed -->

`include/layout_provider.h` 声明抽象 `LayoutProvider`
（`getBlockId/getNumBlocks/getNumNodes/name`），实现 `BfsLayoutProvider`
（从 `route_table.bin` 加载）与 `RandomLayoutProvider`（随机对照）。

## 替换策略 {#API-004}
<!-- ndf: kind=def level=must layer=L1 status=stable since=0.1 source=observed -->

`include/replacement_policy.h` 声明抽象 `ReplacementPolicy`
（`onAccess/selectVictim/onInsert/onRemove/name/size/clear`），实现 `LRUPolicy`、
`LFUPolicy`、`LRUKPolicy`（K=2）。

## 图预取器 {#API-005}
<!-- ndf: kind=def level=must layer=L1 status=stable since=0.1 source=observed -->

`include/graph_prefetcher.h` 声明 `GraphPrefetcher` 与 `Stats`。关键方法：
`submitPrefetch`、`flushSubmits`、`reapCompletions`、`waitForCompletions`、
`waitForBlock`、批量等待。

## io_uring 封装 {#API-006}
<!-- ndf: kind=def level=must layer=L1 status=stable since=0.1 source=observed -->

`include/io_uring_wrapper.h` 声明 `IoUring` 封装（提交 / 回收 / CQE 窥视）。多线程下
io_uring 非线程安全（[[CON-004]]），须 `FINE_PREAD=1` 以 pread 替代。

## SIMD 抽象 {#API-007}
<!-- ndf: kind=def level=must layer=L1 status=stable since=0.1 source=observed -->

`include/simd.h` 按编译期宏分发到 `simd_x86.h`（AVX2）/ `simd_arm.h`（NEON）/
`simd_scalar.h`（标量），提供统一的距离计算与预取原语（`SIMD_PREFETCH`）。

## GBDT 模型 {#API-008}
<!-- ndf: kind=def level=must layer=L1 status=stable since=0.1 source=observed -->

`include/gbdt_model.h` 声明 `gbdt_predict(const float* feat)`，输入 11 维特征
（n_coarse、d0、d9、dk、dk1、gap_ratio、d_mean、d_std、d_cv、d_ratio_01、d_ratio_09），
输出候选数预测值（100 棵树，max_depth=4）。模型训练来源见 [[BEH-010]]。

## 文件格式与 Magic {#API-009}
<!-- ndf: kind=def level=must layer=L2 status=stable since=0.1 source=observed -->

`include/common.h` 声明磁盘文件格式（source=observed）：

- `MAGIC_GRAPH`（"GRPH"）`graph_structure.bin`：`GraphHeader` + 图结构。
- `MAGIC_BLOCKS`（"BHKH"）`blocks.bin`：`BlocksFileHeader`（4096 字节头，O_DIRECT 对齐）。
- `MAGIC_ROUTE`（"ROUT"）`route_table.bin`：node → block 映射。
- `MAGIC_BFS`（"BFS\0"）`bfs.bin`：old↔new 映射。
- 常量：`DEFAULT_BLOCK_SIZE=256KB`、`FORMAT_VERSION=1`、
  `FORMAT_VERSION_COMPRESSED=2`（delta+varint 邻居编码）、`BLOCKS_FILE_HEADER_SIZE=4096`。

## 运行时旋钮接口 {#API-010}
<!-- ndf: kind=def level=must layer=L1 status=stable since=0.1 source=observed -->

搜索 / I/O 行为由环境变量旋钮控制（source=observed）：

| 旋钮 | 默认 | 行为条款 |
|------|------|----------|
| `TWO_STAGE` | 0 | [[BEH-001]] |
| `PQ_CODES_PATH` | 必填 | [[BEH-003]] |
| `REFINE_EF` | 200 | [[BEH-003]] |
| `CACHE_MB` | 必填 | [[BEH-005]] |
| `FLAT_VEC_MB` | 64 | [[BEH-008]] |
| `FINE_RERANK` / `FINE_BUFFERED` / `FINE_PREAD` | 0 | [[BEH-004]] |
| `VEC_BLOCKS_PATH` | 必填 | [[BEH-004]] |
| `L4_WILLNEED` / `WILLNEED_BG` / `PAGE_MERGE_BG` | 0 | [[BEH-007]] |
| `ADAPTIVE_EF` | 0 | [[BEH-009]] |
| `LEARNED_EF` / `GBDT_MARGIN` | 0 / 0.8 | [[BEH-010]] |
| `NUM_THREADS` | 0 | [[BEH-013]] |
| `VL_POOL_THREADS` | 999 | [[BEH-011]] |

## 索引构建流水线工具 {#API-011}
<!-- ndf: kind=def level=must layer=L1 status=stable since=0.1 source=observed -->

`src/pipeline/` 提供 7 步离线构建工具（source=observed）：`build_index`、
`extract_graph`、`bfs_reorder`、`write_blocks_veconly`、`write_blocks` + `gen_route`、
PQ 编码（`scripts/train_pq.py`）、ground truth（`scripts/gen_gt.py`），另有
`prune_graph`、`shuffle_vecblocks`、`cluster_reorder`（`-fopenmp`）、`verify`、
`write_pq_blocks`。三步铁律：一套数据从头到尾、graph 与 blocks 同批生成、PQ 的 M 匹配维度。

## 基准工具 {#API-012}
<!-- ndf: kind=def level=must layer=L1 status=stable since=0.1 source=observed -->

`src/benchmark/` 提供：`benchmark_sustained`（sustained 权威口径）、
`benchmark_diskhnsw`（cache-warmed 回归护栏）、`benchmark_hnswlib_native`
（全内存对照）。见 [[VER-001]]、[[VER-002]]。
