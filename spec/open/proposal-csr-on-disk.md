# 提案：CSR 上磁盘 - L0 邻接表分页加载以压缩 RSS

> track: poc
> explore_surface: graph-structure,io-path,memory-layout
> 提出日期：2026-08-07
> 基线 Trunk：`b7aac90`
>
> Status: Proposed

## 1. 背景与动机

### 1.1 当前内存布局

SIFT1M（1M 节点, 128 维）的常驻内存构成：

| 组件 | 内存 | 说明 |
|------|------|------|
| 上层图+向量 | 30MB | 63001 个 upper-layer 节点的精确向量 |
| **L0 CSR compact** | **47MB** | **delta+varint 压缩邻接表 (21.2M edges)** |
| L0 CSR byte_offsets | 3.8MB | 节点级随机访问索引 (N+1 × uint32) |
| PQ codes | 30MB | 1M × 32 bytes |
| route/slot/labels | 18MB | 块路由 + slot table |
| flat_vec_cache | 64-160MB | LRU 热向量缓存 |
| BlockCache | 64MB | O_DIRECT 块缓存 |
| VisitedList 池 | ~10MB | 多线程搜索去重 |
| **RSS 总计** | **~242MB** | (512MB cgroup 下) |

CSR compact（47MB）占 RSS 的 **19.4%**。在 512MB cgroup 下不是瓶颈，
但规模放大后成为主导：

### 1.2 规模放大投影

| 规模 | CSR compact | byte_offsets | 上层向量 | PQ codes | 总图结构 |
|------|------------|-------------|---------|---------|---------|
| 1M (SIFT) | 47MB | 3.8MB | 30MB | 30MB | 111MB |
| 10M (DEEP) | ~470MB | ~38MB | ~100MB | ~300MB | ~908MB |
| 100M (预估) | **~4.7GB** | **~380MB** | ~300MB | ~3GB | **~8.4GB** |

100M 规模下 CSR compact = 4.7GB，是内存瓶颈（[[DEC-010]]、[[CHR-001]] P3 已识别）。

### 1.3 已有决策铺垫

- [[DEC-010]]: "100M 规模时 CSR 上磁盘是更有效的方案，不需要更高压缩率"
- [[DEC-026]]: P3（100M）需重新评估范式；CSR 上磁盘是图方法延续的前提
- 优化路线图 P3-1: "CSR 上磁盘 + 分页加载, 高复杂度, 🔴 优先级"

### 1.4 当前搜索中的 CSR 访问模式

```
Phase A (PQ 粗筛):
  for each node in search frontier:
    neighbors = decode_csr(node)  // ← 内存随机访问, ~46 bytes/节点
    for each neighbor:
      pq_dist = PQ_ADC(neighbor)  // 纯内存
      candidate_heap.push(neighbor, pq_dist)
```

每个节点的 CSR 邻居列表平均 ~21 条边, 压缩后 ~46 bytes, 变长。
访问模式：**图引导的随机访问**（BFS 重排后空间局部性较好，但非顺序）。

## 2. 方案设计

### 2.1 核心思路

将 `adj_csr_compact_`（压缩字节流）从内存移到磁盘文件，
搜索时按需通过 page cache 读取。

**保留在内存**：
- `adj_csr_byte_offsets_`（3.8MB @ 1M, 380MB @ 100M）— 随机访问索引，太小不值得上磁盘
- 上层图+向量（30MB）— 搜索入口，频繁访问
- PQ codes（30MB）— Phase A 核心，零 I/O 距离计算

**移到磁盘**：
- `adj_csr_compact_`（47MB @ 1M, 4.7GB @ 100M）— 主体压缩邻接表

### 2.2 三种 I/O 路径方案

#### 方案 A: mmap（最简）

```cpp
int fd = open(csr_path, O_RDONLY);
void* csr_mmap = mmap(nullptr, file_size, PROT_READ, MAP_PRIVATE, fd, 0);
madvise(csr_mmap, file_size, MADV_RANDOM);  // 随机访问模式
// 访问: const uint8_t* p = (uint8_t*)csr_mmap + byte_offsets_[new_id];
```

**优点**: 实现极简（~20 行代码），内核管理 page cache，自动 cgroup 记账。
**缺点**: 无法显式控制预取；page cache 与 vecblocks page cache 竞争预算。
**适用**: 快速验证 CSR 上磁盘的可行性和性能影响。

#### 方案 B: 分页 BlockCache（复用基础设施）

将 CSR compact 文件按 64KB 分页，用独立的 BlockCache 或类似机制管理：

```
csr_file: [page_0 | page_1 | ... | page_N]
csr_route: node_id -> page_id, offset_in_page

访问: page = csr_cache.getPage(page_id)
      neighbors = decode(page + offset_in_page)
```

**优点**: 显式控制缓存大小、与 vecblocks BlockCache 独立调优、可复用 LRU 机制。
**缺点**: 需要构建 csr_route 表（N × uint32 page_id），增加复杂度。
**适用**: 生产路径，精细控制。

#### 方案 C: mmap + WILLNEED 预取（混合）

mmap 读取 + 后台线程对即将访问的页做 `madvise(MADV_WILLNEED)`：

```
Phase A 中收集下一批待访问节点的 page range
-> BG 线程 madvise(WILLNEED) 提前触发内核 readahead
-> 搜索线程实际访问时 page cache 已热
```

**优点**: 复用 WILLNEED_BG 的 SPSC 无锁架构；内核 page cache 自动管理。
**缺点**: madvise 粒度是页级（4KB），可能过度预取。
**适用**: 平衡方案，A 的简单性 + B 的预取控制。

### 2.3 推荐执行路径

**R0 先验证方案 A（mmap）**：最小改动，快速确认 CSR 上磁盘的性能影响。
若性能可接受 -> 直接 promote（最简方案）。
若性能不可接受 -> R1 切方案 C（mmap + WILLNEED 预取）。
若仍不可接受 -> R2 切方案 B（分页 BlockCache）。

### 2.4 与现有机制的交互

| 机制 | 交互 |
|------|------|
| WILLNEED_BG (Phase B) | 独立运行, 不冲突; CSR 预取是 Phase A, vecblocks 预取是 Phase B |
| flat_vec_cache | 独立; FVC 缓存向量数据, CSR 缓存邻接表 |
| PQ ADC | 独立; PQ codes 仍在内存, CSR 上磁盘不影响 Phase A 的 PQ 距离计算 |
| ADAPTIVE_EF / GBDT | 独立; 候选数裁剪在 PQ 粗筛后, CSR 解码在裁剪前 |
| cgroup page cache 预算 | ⭐ 关键: CSR page cache 与 vecblocks page cache 共享 cgroup 预算 |

### 2.5 BFS 重排的价值

BFS 重排（[[DEC-006]]）使图上相邻节点在 CSR 文件中物理相邻。
CSR 上磁盘后，搜索访问的邻居节点倾向于落在同一页或相邻页，
**BFS 重排天然提升了 CSR 的 page cache 命中率**。
这是 BFS 重排对 CSR-on-disk 的间接但关键贡献。

## 3. 拟新增条款（draft）

### L0 CSR 邻接表磁盘驻留 {#BEH-036}
<!-- ndf: kind=req level=tbd layer=L1 status=draft since=0.9.12 source=proposed -->
<!-- ndf: topic=csr-on-disk -->

L0 CSR 压缩邻接表 MAY 存储在磁盘文件中，搜索时按需通过 page cache 读取。
`adj_csr_byte_offsets_` MUST 保留在内存中（随机访问索引）。

### CSR 磁盘文件格式 {#API-020}
<!-- ndf: kind=interface level=tbd layer=L1 status=draft since=0.9.12 source=proposed -->
<!-- ndf: topic=csr-on-disk -->

`CSR_FILE_PATH` 环境变量指定 CSR compact 文件路径。
格式：`[N × uint32 max_level] [N × uint64 labels] [upper vectors] [CSR compact bytes]`
（从现有 graph_structure.bin 拆分，或独立文件）。

## 4. 实验计划

### R0: mmap 基线验证
- 将 `adj_csr_compact_` 改为 mmap 读取
- SIFT1M 512MB + 256MB cgroup, sustained benchmark
- 对比: BASE (CSR in-mem) vs CSR-on-disk (mmap)
- **验收**: recall 不变（CSR 内容未变）；QPS 下降幅度量化
- **预期**: BFS 重排使 page cache 命中率较高，QPS 下降 < 30%

### R1: 性能影响分析
- 若 R0 QPS 下降 > 30%: 分析 page cache 命中率（mincore）、majfault 率
- 测量 CSR 访问的 I/O 量 vs vecblocks I/O 量
- **验收**: 明确瓶颈是 CSR I/O 还是 page cache 竞争

### R2: mmap + WILLNEED 预取
- 实现 Phase A 的 BG 线程 madvise(WILLNEED) 预取
- 复用 WILLNEED_BG 的 SPSC 架构
- **验收**: QPS 恢复到 R0 基线的 90%+

### R3: 256MB 极限内存验证
- 在 256MB cgroup 下 CSR + vecblocks 共享 page cache 预算
- **关键问题**: CSR page cache 挤压 vecblocks page cache?
- **验收**: QPS 不低于现 256MB baseline 的 70%

### R4: DEEP10M 验证（如时间允许）
- 10M 规模下 CSR = ~470MB, 更能体现 CSR 上磁盘的价值
- **验收**: RSS 显著下降, recall ≥ 95%

## 5. 晋升条件

若以下全部满足，另开 promote 提案：

1. recall ≥ 95%（sustained, 不变）
2. QPS 下降 < 30%（512MB cgroup, vs CSR in-mem baseline）
3. RSS 下降 ≥ 40MB（SIFT1M, CSR compact 移出内存）
4. 无 page cache 灾难性竞争（256MB cgroup 下可工作）

若 QPS 下降 > 50% 且无法通过预取缓解 -> 走 §6.2d 负结果闭环。

## 6. 不做的事

- 不改 Trunk `src/`（POC 阶段, [[BEH-018]] 第 6 条）
- 不改上层图+向量（保持内存常驻）
- 不改 PQ codes（保持内存常驻）
- 不改 byte_offsets（保持内存常驻, 随机访问索引）
- 不引入新的压缩算法（delta+varint 已足够, [[DEC-010]]）
- 不在 POC 阶段考虑 100M 规模（先 1M 验证可行性）

## 7. 表面冲突检查

活跃 exploring 主题扫描结果：**无活跃 exploring 主题**（全部 promoted/rejected/closed）。

本主题 `explore_surface: graph-structure,io-path,memory-layout`：
- 与已 promoted 的 `l4-cache-mgmt`（surface: page-cache-l4）相交于 page cache 管理
  - 判定：**不冲突**。l4-cache-mgmt 关注 vecblocks page cache，本主题关注 CSR page cache，是叠加关系
- 与已 promoted 的 `sustained-query-benchmark`（surface: test-infra）为**依赖关系**
  - 本主题 MUST 用 sustained 口径测量（[[CON-SLA-020]]）
- 与已 promoted 的 `multi-thread-scaling`（surface: mt-scaling）为**叠加关系**
  - CSR 上磁盘后多线程行为需验证，但不竞争同一探索面

## 8. 影响的既有条款

POC 阶段 MUST NOT 修改 stable 条款。若 promote，将影响：

| 条款 | 影响 |
|------|------|
| [[BEH-003]] (Phase A 搜索) | CSR 访问路径从内存改为磁盘/mmap |
| [[CON-SLA-014]] (cgroup 隔离) | page cache 预算新增 CSR pages |
| [[CON-SLA-016/017/018/020]] | SLA 数字需重测（RSS 下降, QPS 可能下降） |
| [[DEC-010]] | "100M CSR 上磁盘" 从远期计划变为已验证机制 |

## 9. 风险

| 风险 | 概率 | 缓解 |
|------|------|------|
| CSR 随机访问导致 page cache 效率低 | 中 | BFS 重排提升局部性; R1 分析命中率 |
| CSR + vecblocks page cache 竞争 | 高 | 256MB cgroup 下验证; 可设 mmap MADV_DONTNEED 回收冷页 |
| mmap 在 cgroup v1 下记账行为差异 | 低 | cgroup-v1-support (API-016) 已覆盖 |
| 100M 规模 byte_offsets 380MB 过大 | 低 | P3 可考虑上磁盘或压缩; 本 POC 先不处理 |

## 10. 数据文件

CSR compact 可从现有 `graph_structure.bin` 提取，或构建时独立输出：

```bash
# 从现有 graph 文件提取 CSR compact 独立文件
./build/extract_csr output/sift1m_graph.bin output/sift1m_csr_compact.bin
# 产出: [N × uint32 max_level] [N × uint64 labels] [upper vectors] [CSR compact bytes]
```

需新增 pipeline 工具 `extract_csr`（或复用 `extract_graph` 扩展）。
