# Constraints — 硬编码阈值与限制

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

## Page Search SLA 豁免 {#CON-SLA-008}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.2 source=deduced -->
<!-- ndf: refines=DEC-017,CON-007 -->

当 `PAGE_SEARCH=1` 时，Buffered QPS SLA 放宽为 ≥ 基线 × 85%（当前实测 1832/2051 = 89%，达标）。
recall SLA 不变（≥ 95%，实测 96.20%）。

当 `PAGE_SEARCH=0`（默认）时，Buffered 原始 SLA（QPS ≥ 2000）不变。Honest / O_DIRECT 下限见 [[CON-SLA-011]]。

> rationale: Page Search 是 opt-in recall 提升功能，用 ~15% QPS 换 0.5pp recall。
> 适合 recall 优先于速度的场景。参见 [[DEC-020]]。

## Dynamic Width 已知限制 {#CON-SLA-009}
<!-- ndf: kind=info level=may layer=L1 status=deprecated since=0.2 source=deduced -->
<!-- ndf: refines=DEC-019,CON-007 depends-on=DEC-024 -->

Dynamic Width 在当前配置（REFINE_EF=100, PQ 粗筛）下无效果。根因：PQ 近似距离的
浮点波动导致 top-K 持续抖动，收敛检测（hash + lowerBound delta）从未触发。

**不纳入 SLA 考核**。代码保留默认关闭（`DYNAMIC_WIDTH=0`），零开销。[[DEC-024]] 已正式放弃；
对应行为条款 [[BEH-015]] 为 `deprecated`。

未来方向：如果 REFINE_EF 降到 30-50，或改用精确距离搜索，DW 可能生效。

## 冷 I/O 模式 SLA {#CON-SLA-010}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.3 source=deduced -->
<!-- ndf: refines=DEC-021 -->

当 `EVICT_PAGE_CACHE=1` 时：
- Recall SLA 不变（≥ 95%）
- Buffered QPS SLA 放宽为 ≥ 500（冷 I/O 条件下 QPS 自然下降）
- RSS SLA 不变（≤ 300MB）

| 参数 | 默认值 | 环境变量 | 说明 |
|------|--------|---------|------|
| Page Cache 驱逐开关 | `0` (关) | `EVICT_PAGE_CACHE` | 1=每次查询后 posix_fadvise(DONTNEED) 驱逐 vecblocks |

> rationale: 冷 I/O 下 Fine Rerank 每页读取 ~10-50μs（vs 热态 ~1μs），
> QPS 下降是预期行为。QPS ≥ 500 对应 < 2ms/query，仍为交互式可用。

## 诚实 I/O 基准协议 {#CON-HONEST-002}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.5 source=deduced -->
<!-- ndf: refines=DEC-030,DEC-039 -->

性能基准测试 MUST 至少报告两组数据：
1. **Buffered**: `FINE_BUFFERED=1`（含 page cache）
2. **Direct**: `FINE_DIRECT=1`（O_DIRECT，无 page cache）

两组模式 MUST 在同一 cgroup 限制下运行。Buffered 模式下，page cache 计入
cgroup 内存使用，运行过程中峰值内存（anon + file）MUST NOT 超过 cgroup 限制。

报告 MUST 标注测量模式。仅报告 Buffered 模式数字时 MUST 附带声明：
"此数字在 cgroup 限制内运行，page cache 与匿名内存共享内存预算"。

> rationale: cgroup v2 的 memory.max 同时限制匿名内存和 page cache。Buffered
> 模式是生产推荐路径，page cache 是 OS 免费提供的冷热分层，但它消耗的是
> cgroup 内存预算，不是无限制的白嫖。O_DIRECT 模式消除 page cache 后，
> 测量的是纯匿名内存 + 真实磁盘 I/O 的性能，代表最差情况。
> 关联提案: proposal-odirect-benchmark.md（已归档）

## Honest / O_DIRECT QPS 下限 {#CON-SLA-011}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.5 source=deduced -->
<!-- ndf: refines=CON-HONEST-002 depends-on=DEC-039,DEC-057 -->

SIFT1M、512MB cgroup、`FINE_DIRECT=1`（Honest / O_DIRECT）下：

| 指标 | 下限 | 实测锚点 (2026-07-31) |
|------|------|----------------------|
| QPS (单线程) | ≥ 100 | 130 |
| QPS (4 线程) | ≥ 400 | 502 |
| Recall@10 | ≥ 95% | 95.70% |

Buffered 模式阈值仍以 [[CHR-006]] Buffered 行及 [[CON-SLA-008]]…[[CON-SLA-010]] 为准，MUST NOT 用本条款覆盖。

> rationale: 双轨 SLA——不静默删除 Buffered 数字；Honest 下限取自 O_DIRECT 实测并留安全余量。
