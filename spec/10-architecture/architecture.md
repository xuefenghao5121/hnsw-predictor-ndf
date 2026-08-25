# DiskHNSW — Architecture

> scope: product (10-architecture)
> status: stable | perf: not-established | bootstrap: adopt
> Observed Trunk SHA: `d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755`

本文件描述 observed Trunk 的模块分解、内存分层与数据流。

## 模块分解 {#ARCH-001}
<!-- ndf: kind=arch level=must layer=L1 status=stable since=0.1 source=observed -->

observed Trunk 分解为四个子模块组：

| 组 | 路径 | 职责 |
|----|------|------|
| core | `src/core/{disk_hnsw,block_cache,graph_prefetcher}.cpp` | 搜索引擎主体、块缓存、图预取 |
| pipeline | `src/pipeline/*.cpp` | 索引构建流水线（建图→提取→BFS→分块→PQ） |
| benchmark | `src/benchmark/*.cpp` | sustained 权威基准 + cache-warmed 回归基准 + hnswlib 对照 |
| test | `src/test/*.cpp` | 单元 / 质量测试 |

公开接口集中于 `include/`（14 个头文件），见 `spec/30-interfaces/`。

## 内存驻留分层 {#ARCH-002}
<!-- ndf: kind=arch level=must layer=L2 status=stable since=0.1 source=observed -->

DiskHNSW MUST 将数据分为常驻内存层与按需 I/O 层：

- **常驻内存（SIFT1M 约 155–242MB）**：上层图 + 上层向量、L0 邻接表 CSR 压缩、
  PQ codes、route/slot/labels、flat_vec_cache、VisitedList 池、BlockCache。
- **按需 I/O**：VecBlocks（磁盘，496MB）经 Fine Rerank 以 4KB 页读取，WILLNEED 预取、
  PAGE_MERGE_BG 合并连续页。

> rationale: 图结构与 PQ 常驻内存使搜索的"导航"无需 I/O；仅精确距离计算触发 I/O。

## 两阶段搜索数据流 {#ARCH-003}
<!-- ndf: kind=arch level=must layer=L2 status=stable since=0.1 source=observed -->

```text
query
 ├─ Step 1 贪心下降（纯内存）→ 上层图找 Layer 0 入口
 ├─ Step 2 Phase A PQ 粗筛（纯内存）→ CSR 邻接遍历 + PQ ADC → top-N 候选
 └─ Step 3 Phase B 精确精排（按需 I/O）
     flat_vec_cache 命中? → 跳过 I/O
     miss → WILLNEED_BG 预取 → pread 4KB 页 → 精确 L2 → top-K
```

对应行为条款：[[BEH-001]]、[[BEH-002]]、[[BEH-003]]、[[BEH-004]]。

## I/O 优化层次 {#ARCH-004}
<!-- ndf: kind=arch level=must layer=L2 status=stable since=0.1 source=observed -->

| 层级 | 机制 | 行为条款 |
|------|------|----------|
| flat_vec_cache | 进程内 LRU 热向量缓存 | [[BEH-008]] |
| WILLNEED | `fadvise(WILLNEED)` 内核异步 readahead | [[BEH-007]] |
| WILLNEED_BG | 无锁 SPSC 后台线程提交预取 | [[BEH-007]] |
| PAGE_MERGE_BG | 合并连续页减少 syscall | [[BEH-007]] |
| VL_POOL | 自适应 VisitedList 池化 | [[BEH-011]] |
| ADAPTIVE_EF | PQ gap 启发式候选数 | [[BEH-009]] |
| LEARNED_EF | GBDT 多特征候选数预测 | [[BEH-010]] |

> 各机制收益须以 sustained 口径重新测量（cache-warmed 收益不可直接引用，见 [[DEC-002]]）。

## 可插拔设计 {#ARCH-005}
<!-- ndf: kind=arch level=must layer=L2 status=stable since=0.1 source=observed -->

BlockCache MUST 通过抽象接口解耦两个变化维度：

1. **布局编排器** `LayoutProvider`（[[API-003]]）：`BfsLayoutProvider`（生产）、
   `RandomLayoutProvider`（对照）。
2. **替换策略** `ReplacementPolicy`（[[API-004]]）：`LRUPolicy`（默认）、
   `LFUPolicy`、`LRUKPolicy`。

## SIMD 抽象层 {#ARCH-006}
<!-- ndf: kind=arch level=must layer=L2 status=stable since=0.1 source=observed -->

距离计算 MUST 经 `include/simd.h` 在编译期按目标架构分发：

- `__x86_64__` → `simd_x86.h`（AVX2 256-bit）
- `__aarch64__` / `__arm__` → `simd_arm.h`（NEON 128-bit）
- 其它 → `simd_scalar.h`（标量 fallback）

索引 / 图 / PQ 编码为跨架构兼容的二进制格式。见 [[API-007]]、[[BEH-016]]。

## 分层 Vamana 建图与上层驻留 {#ARCH-007}
<!-- ndf: kind=arch level=must layer=L2 status=stable since=0.2 source=promote -->

建图（[[BEH-027]]）产出分层图结构：上层（Layer 1+）邻接常驻内存（贪心下降无 I/O，
[[BEH-002]]），L0 密图经 BFS 重排 / 分块落盘，布局与现有 DiskHNSW 块布局兼容
（[[ARCH-002]]、[[ARCH-003]]）。

```text
build_index (HNSW 层分配 + 每层 Vamana)
  └─ GraphStructure（上层邻接内存驻留 + L0 CSR）
       └─ bfs_reorder → write_blocks / write_blocks_veconly / gen_route → PQ
            └─ DiskHNSW 搜索（上层内存下降 → L0 + Fine Rerank / BlockCache）
```

原 `extract_graph`（hnswlib 索引 → GraphStructure）步骤已并入 `build_index`；搜索路径复用不变。

> source: poc/hierarchical-vamana/ndf/TOPIC.md ; spec/open/proposal-promote-hierarchical-vamana.md @ d0ae5dd
> track: promote ; Topic: hierarchical-vamana
