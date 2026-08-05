# Constraints — 常量与默认参数

> 条款索引: `CON-001`, `CON-002`, `CON-003`, `CON-004`, `CON-005`, `CON-006`, `CON-007`

## 文件格式常量 {#CON-001}
<!-- ndf: kind=constraint level=must layer=L2 status=stable since=0.1 source=observed -->

| 常量 | 值 | 定义位置 | 说明 |
|------|-----|---------|------|
| `MAGIC_GRAPH` | `0x47524148` | `common.h:18` | "HARG" (GRPH reversed) |
| `MAGIC_BLOCKS` | `0x424C4B48` | `common.h:19` | "HKLB" (BLKH reversed) |
| `MAGIC_ROUTE` | `0x524F5554` | `common.h:20` | "ROUT" |
| `MAGIC_BFS` | `0x42465300` | `common.h:21` | "BFS\0" |
| `FORMAT_VERSION` | `1` | `common.h:23` | 非压缩格式 |
| `FORMAT_VERSION_COMPRESSED` | `2` | `common.h:24` | delta+varint 压缩 |
| `DEFAULT_BLOCK_SIZE` | `262144` (256KB) | `common.h:27` | 默认块大小 |
| `BLOCKS_FILE_HEADER_SIZE` | `4096` | `common.h:31` | O_DIRECT 对齐保留 |
| `FLAG_NEIGHBOR_DELTA_VARINT` | `0x01` | `common.h:78` | 邻接表压缩标志 |
| `FLAG_VEC_ONLY` | `0x02` | `common.h:79` | Vec-only block 标志 |

## 内存与缓存限制 {#CON-002}
<!-- ndf: kind=constraint level=must layer=L2 status=stable since=0.1 source=observed -->

| 常量 | 值 | 定义位置 | 说明 |
|------|-----|---------|------|
| Default cache_slots | `64` | `block_cache.h:142` | 约 16MB @ 256KB block |
| Default dim | `128` | `block_cache.h:143` | SIFT 默认维度 |
| Default flat_vec_cache | `4 MB` | `block_cache.cpp:244` | 可被 `FLAT_VEC_MB` 覆盖 |
| io_uring ring size | `128` | `graph_prefetcher.h:52` | SQ/CQ 条目数 |
| io_uring buffer alignment | `512` | `io_uring_wrapper.h:164` | O_DIRECT 最小对齐 |
| Max recent accesses | `1024` | `block_cache.h:385` | 访问历史记录上限 |
| `flat_block_num_slots_` | `cache_slots_ * 4` | `block_cache.cpp:284` | Flat block ptr cache 大小 |

## 搜索参数默认值 {#CON-003}
<!-- ndf: kind=constraint level=should layer=L2 status=stable since=0.1 source=observed -->

| 参数 | 默认值 | 定义位置 | 说明 |
|------|--------|---------|------|
| `ef_search_` | `10` | `disk_hnsw.cpp:40` | 构造函数默认值 |
| `REFINE_EF` | `200` | `disk_hnsw.cpp:1647` | 两阶段粗筛 ef |
| `kLookaheadHops` | `0` | `disk_hnsw.cpp:438` | 默认为 0 (关闭 lookahead) |
| `kPfDist` | `6` | `disk_hnsw.cpp:641` | SW 预取 pipeline 距离 |
| pq `nbits` | `8` | `disk_hnsw.cpp:192` | ksub = 2^8 = 256 |
| `SPEC_PREFETCH` 节流 | `16` | `disk_hnsw.cpp:690` | 每 16 轮触发一次 |
| `BEAM_WIDTH` | `0` | `disk_hnsw.cpp:1621` | 0=标准 best-first |
| `NONBLOCK` | `0` | `disk_hnsw.cpp:1627` | 0=阻塞搜索 |
| `BATCH_IO_N` | `0` | `disk_hnsw.cpp:1633` | 0=关闭批量 I/O |

## 热度评估阈值 {#CON-004}
<!-- ndf: kind=constraint level=should layer=L2 status=stable since=0.1 source=observed -->

| 阈值 | 值 | 定义位置 | 说明 |
|------|-----|---------|------|
| Decay factor | `0.995` | `block_heat_evaluator.h:14` | 每次查询衰减因子 |
| Hot threshold | `> 10.0` | `block_heat_evaluator.h:82` | heat > 10 = hot |
| Warm threshold | `> 1.0` | `block_heat_evaluator.h:83` | 1 < heat <= 10 = warm |
| Cold threshold | `<= 1.0` | `block_heat_evaluator.h:84` | heat <= 1 = cold |
| Median cutoff | `> 0.01` | `block_heat_evaluator.h:62` | 计算中位数时过滤极低值 |
| Heat-weighted evict check | `> 5 queries` | `block_cache.cpp:572` | 热度加权淘汰阈值 |

## Build Pipeline 固定参数 {#CON-005}
<!-- ndf: kind=constraint level=must layer=L2 status=stable since=0.1 source=observed -->

| 参数 | 值 | 定义位置 | 说明 |
|------|-----|---------|------|
| Build M | `16` | `build_pipeline.sh:44` | HNSW 建图 M 参数 |
| ef_construction | `200` | `build_pipeline.sh:44` | 建图 ef |
| Block size (pipeline) | `65536` | `build_pipeline.sh:30` | 64KB |
| SIFT default M (PQ) | `32` | `train_pq.py:72` | dim=128, dsub=4 |
| Deep default M (PQ) | `8` | `train_pq.py:74` | dim=96, dsub=12 |
| GT default K | `10` | `gen_gt.py:52` | 缺省 top-10 |

## C++ 编译约束 {#CON-006}
<!-- ndf: kind=constraint level=must layer=L2 status=stable since=0.1 source=observed -->

| 约束 | 值 | 定义位置 | 说明 |
|------|-----|---------|------|
| C++ standard | `c++17` | `Makefile:2` | `-std=c++17` |
| Optimization | `-O3` | `Makefile:2` | 最高优化级别 |
| Architecture | `native` | `Makefile:2` | `-march=native` (AVX2) |
| Warnings | `-Wall -Wextra` | `Makefile:2` | 严格警告 |
| Threads | `-pthread` | `Makefile:3` | POSIX 线程 |
| Linux kernel | `5.1+` | `io_uring_wrapper.h:13` | io_uring 系统调用 |

## Page Search / Dynamic Width 参数 {#CON-007}
<!-- ndf: kind=constraint level=should layer=L2 status=stable since=0.2 source=deduced -->

| 参数 | 默认值 | 环境变量 | 说明 |
|------|--------|---------|------|
| Page Search 开关 | `0` (关) | `PAGE_SEARCH` | 1=开启 Fine Rerank 页内全向量扫描 |
| Dynamic Width 开关 | `0` (关) | `DYNAMIC_WIDTH` | 1=开启自适应 efSearch |
| DW 收敛跳数 | `10` | `DW_CONVERGE_HOP` | 连续 N 跳 top-K 无变化触发收窄 |
| DW 衰减率 | `0.75` | `DW_DECAY` | 几何衰减因子 |
| DW 最小 efSearch | `32` | `EF_SEARCH_MIN` | 收窄下限 |

> 注: 以上参数为 SHOULD 级别（实验性），benchmark 验证后决定是否默认开启。
> 当前实测: PAGE_SEARCH QPS -19%（SLA 违规），DYNAMIC_WIDTH 无效果。

