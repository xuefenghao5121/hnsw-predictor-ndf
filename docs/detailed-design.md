# DiskHNSW 详细设计文档

> 版本: v2.0 | 日期: 2026-08-06
> 基于 Trunk commit 476b953 (WILLNEED_BG + PAGE_MERGE_BG + VL_POOL + FineRerank race fix)

---

## 1. 系统目标

在 cgroup 内存限额下，使用磁盘驻留向量数据，实现与全内存 HNSW 可比的搜索召回率（≥95%），
同时将常驻内存控制在限额内。

**核心指标（SIFT1M, 严格 cgroup 隔离, 200q 标准数据集）:**

> **注**: 200q 为 cache-warmed 场景 ([[DEC-083]]).
> GBDT (LEARNED_EF) 在 I/O bound 场景的相对增益 +33~124% (recall ≥ 95%).

| 配置 | 指标 | 目标 | 实测 |
|------|------|------|------|
| 512MB 1T | Recall@10 | ≥95% | 95.75% |
| 512MB 1T | QPS | ≥2000 | 3,366 |
| 512MB 16T | QPS | ≥20000 | 30,332 |
| 256MB 16T | QPS | ≥10000 | 18,675 |
| 256MB | RSS | ≤256MB | 223MB |
| 所有配置 | oom | =0 | 0 |

**对比 hnswlib**: hnswlib 需 732MB RSS (OOM@512MB)，DiskHNSW 内存节省 2.9× (512MB) / 5.7× (256MB)。

---

## 2. 架构概览

### 2.1 模块分层

```
┌─────────────────────────────────────────────────────────────┐
│ 应用层: benchmark, tests, pipeline tools                    │
├─────────────────────────────────────────────────────────────┤
│ 搜索引擎 DiskHNSW                                           │
│   两阶段搜索: PQ 粗筛 → Fine Rerank 精排                    │
│   I/O 优化: WILLNEED_BG + PAGE_MERGE_BG + flat_vec_cache   │
│   多线程: per-thread SPSC slots + VL_POOL 自适应池化        │
├─────────────────────────────────────────────────────────────┤
│ 缓存层: BlockCache (O_DIRECT, 64KB) + FlatVecCache (LRU)    │
├─────────────────────────────────────────────────────────────┤
│ I/O 层: GraphPrefetcher (io_uring, PQ 模式禁用)             │
│         Fine Rerank I/O (pread + WILLNEED_BG fadvise)       │
├─────────────────────────────────────────────────────────────┤
│ 数据格式: common.h (fvecs, varint, CSR, BFS reorder)        │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 内存布局

**常驻内存 (SIFT1M, ~155-242MB):**

| 组件 | 大小 | 说明 |
|------|------|------|
| 上层图 + 向量 | 30MB | Layer 1+ 节点（贪心下降用） |
| L0 CSR 邻接表 | 47MB | Delta+Varint 压缩 (1.8× 压缩比) |
| PQ Codes | 30MB | M=32 子量化器编码（全量常驻） |
| flat_vec_cache | 64-160MB | 热向量 LRU 缓存（命中跳过 I/O） |
| route/slot/labels | 18MB | 双路由表 + slot 偏移 + 标签映射 |
| VisitedList 池 | ~10MB | uint8 访问标记（thread_local 池化） |
| BlockCache | 64MB | 64KB 块 LRU 缓存（O_DIRECT） |

**按需 I/O (page cache 热区):**

| 组件 | 大小 | 说明 |
|------|------|------|
| VecBlocks | 496MB | BFS 重排后的 4KB 向量页（Fine Rerank 读取） |

**R5c mincore 诊断 (256MB cgroup):**
- vecblocks 总页数: 126,993
- page cache 命中: 12.1% (15,355 页)
- 磁盘 I/O: 87.9% 需读取
- refault_file: 725 (WILLNEED_BG 已消除容量缺失)
- pgmajfault: ~25/query (冷缺失，不可优化)

### 2.3 两阶段搜索流程

```
查询到达
  │
  ├─ Step 1: 贪心下降 [纯内存]
  │   上层图 (Layer 1+) 遍历，找 Layer 0 入口节点
  │
  ├─ Step 2: Phase A - PQ 粗筛 [纯内存, 无 I/O]
  │   buildPqDistTable(query) → SIMD 查表
  │   searchLayer0():
  │     CSR 邻接表遍历 + PQ ADC 近似距离
  │     _mm_prefetch: route_table + PQ codes (CPU L1/L2)
  │     → 产出 top-EF 候选集 (cand_ids)
  │
  └─ Step 3: Phase B - 精确精排 [按需 I/O]
      │
      ├─ 收集 pages_needed (查 vec_route_table_)
      │
      ├─ WILLNEED_BG: 搜索线程提交页号到 SPSC slot
      │   BG 线程: yield 轮询 → fadvise(WILLNEED) 逐页/合并
      │   内核: 异步 readahead
      │
      ├─ pread: 逐页读 (固定顺序, 阻塞等待 readahead)
      │   page_cache 命中? → 内存拷贝 (快)
      │   miss? → 磁盘 I/O (阻塞)
      │
      └─ 精确 L2 重排 → top-K 结果
```

### 2.4 I/O 优化机制详解

#### flat_vec_cache (DEC-068)

进程内 LRU 缓存，存储 Fine Rerank 中访问过的热向量。
- 粒度: 单向量 (SIFT: 512 bytes)
- 命中率: 45.7% (SIFT1M 256MB)
- 效果: 256MB 下 7.5× QPS (减少 pread)
- 配置: `FLAT_VEC_MB` (256MB 推荐 64, 512MB 推荐 160)

#### WILLNEED (DEC-070)

`posix_fadvise(POSIX_FADV_WILLNEED)` 在 pread 前批量调用，
内核启动异步 readahead，pread 从阻塞磁盘 I/O 变为内存拷贝。

- 适用条件: page cache 严重受限 + pread 是瓶颈 + refault 暴涨
- 效果: 256MB 下 17.7× QPS, 512MB 下 +5.5%, DEEP10M 下 ~0%
- 配置: `L4_WILLNEED=1`

#### WILLNEED_BG (DEC-074, BEH-027)

无锁后台线程替代主线程 fadvise 调用，消除内核锁竞争。

- 架构: Per-thread SPSC slot + atomic flag (零 mutex)
  - 搜索线程: 写页号到 slot → 设 ready flag → 继续 pread
  - BG 线程: yield 轮询 → 处理 ready slot → fadvise
- 效果: 16T 下 +72.8% QPS (vs 主线程 fadvise)
- 配置: `WILLNEED_BG=1`

#### PAGE_MERGE_BG (DEC-075, BEH-028)

在 WILLNEED_BG 线程中合并连续页为单次 fadvise 调用，减少 syscall 数量。

- 效果: 256MB 16T 下 +17.5% QPS
- 注意: 512MB 下有害 (-2.9%)，仅 256MB 推荐
- 配置: `PAGE_MERGE_BG=1` (需 `WILLNEED_BG=1` 前置)

#### VL_POOL (DEC-074, BEH-027)

自适应 VisitedList 池化，避免高并发下频繁内存分配。

- 机制: thread_local VisitedList 复用，T≥阈值时启用
- 效果: 12T 下 +7.1% QPS
- 配置: `VL_POOL_THREADS=14` (推荐)

### 2.5 GraphPrefetcher (PQ 模式下禁用)

GraphPrefetcher 使用 io_uring + O_DIRECT 预取 64KB 图块。
在 PQ 模式下，图遍历使用 CSR 内存邻接表 + PQ ADC 距离，不需要读取向量块，
因此 GraphPrefetcher 被条件禁用 (`!pq_enabled_`)。

Fine Rerank 的 I/O 由 WILLNEED_BG + pread 处理。
GraphPrefetcher 的 io_uring 机制可作为未来 Fine Rerank I/O 优化的参考
(per-thread io_uring 替代 WILLNEED_BG + pread)。

---

## 3. 数据 Pipeline（7 步）

```
base.fvecs
  │
  ├─ Step 1: build_index (hnswlib M=16 efC=200)
  │    └─ index.bin
  ├─ Step 2: extract_graph (maxM=128)
  │    └─ graph.bin [slim+adj 格式: 上层向量 + L0 邻接表]
  ├─ Step 3: bfs_reorder
  │    └─ bfs.bin (old↔new 映射, 提升空间局部性)
  ├─ Step 4: write_blocks_veconly (blockSize=64KB)
  │    └─ vecblocks_64k.bin (Fine Rerank 数据源)
  ├─ Step 5: write_blocks + gen_route
  │    └─ blocks_64k.bin + route_64k.bin (BlockCache 用)
  ├─ Step 6: train_pq (faiss, M=32)
  │    └─ pqco_*_M32_correct.bin (PQ 编码)
  └─ Step 7: gen_gt
       └─ gt200.bin (Ground Truth)
```

**关键**: vecblocks 和 blocks 是两个独立文件，各有独立 route 表，block_id 不一致。

---

## 4. 多线程架构

### 4.1 线程模型

```
主线程
  ├─ 搜索线程 × N (NUM_THREADS)
  │   每线程独立: VisitedList (pool), candidate_set, top_candidates
  │   共享: BlockCache (O_DIRECT, 线程安全), CSR 邻接表 (只读)
  │
  └─ WILLNEED_BG 线程 × 1
      SPSC slots: 每搜索线程一个 slot
      轮询 → fadvise → 内核 readahead
```

### 4.2 FineRerank 线程安全

`buildFineRerank()` 懒初始化使用 `std::call_once` 保证多线程安全。
`pread` 天然线程安全。io_uring 路径 (`vec_ring_`) 非线程安全（共享 SQ/CQ），
多线程必须使用 `FINE_PREAD=1`。

### 4.3 扩展性

| 线程数 | 512MB QPS | 256MB QPS | Scaling |
|--------|-----------|-----------|---------|
| 1T | 3,366 | 2,830 | 1.0× |
| 4T | 9,041 | 7,721 | 2.7× |
| 8T | 14,901 | - | 4.4× |
| 12T | 18,459 | 13,799 | 5.5× |
| 16T | 30,332 | 18,675 | 9.0× |
| 24T | 29,738 | - | 8.8× |

---

## 5. cgroup 严格隔离协议

### 5.1 测试协议 (CON-SLA-014)

1. `sync; echo 3 > /proc/sys/vm/drop_caches` 清场
2. 创建 cgroup: `memory.max = 限制值`
3. 进程写入 cgroup.procs
4. 运行 benchmark
5. 检查: `memory.peak ≤ memory.max`, `memory.events.oom = 0`

### 5.2 SLA 清单

| SLA | 配置 | Recall | QPS | 内存 |
|-----|------|--------|-----|------|
| CON-SLA-014 | SIFT1M 512MB 1T | ≥95% | ≥2000 | ≤512MB |
| CON-SLA-016 | SIFT1M 256MB 4T | ≥95% | ≥5000 | ≤256MB |
| CON-SLA-017 | SIFT1M 512MB 16T | ≥95% | ≥20000 | ≤512MB |
| CON-SLA-018 | SIFT1M 256MB 16T+merge | ≥95% | ≥12000 | ≤256MB |

---

## 6. 已知限制

1. **vecblocks 与 route table 必须配套** - 混用不同版本导致 offset 错误
2. **io_uring 非线程安全** - 多线程必须 `FINE_PREAD=1`
3. **blocks 和 vecblocks 的 block_id 不一致** - 各有独立 route 表
4. **PAGE_MERGE_BG 仅 256MB 推荐** - 512MB 下排序开销 > syscall 节省
5. **WILLNEED 在 I/O 量主导场景无效** - DEEP10M 瓶颈是 majfault 总量 (68K)
6. **Fine Rerank I/O 路径** - WILLNEED_BG + pread 存在 BG 轮询延迟和 pread 顺序阻塞

---

## 7. 优化历程与方向

### 已完成

| 阶段 | 优化 | 效果 | 决策 |
|------|------|------|------|
| P0 | CSR 压缩 | RSS 337→269MB | DEC-006 |
| P0.5 | 双路由表修复 | recall 修复 | DEC-012 |
| P1 | VisitedList uint32→uint8 | 2× QPS | DEC-034 |
| P1 | Fine Rerank pread 修复 | recall 70→95% | DEC-035 |
| P1 | PQ dsub=3 SIMD | +5% QPS | DEC-036 |
| P2 | flat_vec_cache | 7.5× QPS @256MB | DEC-068 |
| P2 | WILLNEED | 17.7× QPS @256MB | DEC-070 |
| P2 | FineRerank 线程安全 | 4T+ 稳定 | DEC-073 |
| P2 | FVC 默认 64MB | +23.4% QPS | DEC-073 |
| P2 | WILLNEED_BG (A2) | +72.8% QPS @16T | DEC-074 |
| P2 | VL_POOL (C2) | +7.1% QPS @12T | DEC-074 |
| P2 | PAGE_MERGE_BG | +17.5% QPS @256MB | DEC-075 |
| P2 | L4 cache 诊断 | Pareto 前沿确认 | BEH-024 |

### 探索中

| 方向 | 描述 | 预期 |
|------|------|------|
| Fine Rerank io_uring | per-thread io_uring 替代 WILLNEED_BG+pread | +5-20% QPS |
| 自适应 EF | PQ 距离间隙启发式调整 REFINE_EF | +15-25% QPS |
| Fine Rerank 早终止 | 连续无改善即停止 | -20-40% I/O |

### 未来

| 阶段 | 描述 |
|------|------|
| P3 | CSR 上磁盘 (100M 规模) |
| P4 | 分级存储 (hot/warm/cold) |
| P5 | SPDK / GPU / NUMA 亲和 |
