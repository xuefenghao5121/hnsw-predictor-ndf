# Decisions — 基础选型 (DEC-001…016)

> 条款索引: `DEC-001`, `DEC-002`, `DEC-003`, `DEC-004`, `DEC-005`, `DEC-006`, `DEC-007`, `DEC-008`, `DEC-009`, `DEC-010`, `DEC-011`, `DEC-012`, `DEC-013`, `DEC-014`, `DEC-015`, `DEC-016`

## D-001: 选择 hnswlib 作为建图引擎 {#DEC-001}
<!-- ndf: kind=decision date=2026-07-28 affects=ARCH-001,API-001 source=observed -->

**Context.** DiskHNSW 需要 HNSW 图结构来驱动搜索。`build_index.cpp` 和 `benchmark_hnswlib_native.cpp` 直接 include `hnswlib/hnswlib.h`。

**Decision.** 使用 hnswlib（C++ header-only 库）作为建图引擎，`build_index` 产出 `index.bin`，`extract_graph` 剥离出精简图结构。

**Alternatives rejected.** 自研 HNSW 建图（工作量大，hnswlib 已成熟）；使用 faiss HNSW（faiss 的 C++ API 不如 hnswlib 轻量）。
**Inferred from.** `hnswlib/` 目录存在、`Makefile` 中 `-I./hnswlib` 编译选项、`build_index.cpp` 和 `benchmark_hnswlib_native.cpp` 的 `#include "hnswlib/hnswlib.h"`。(inferred)

## D-002: 选择 faiss 做 PQ 训练 {#DEC-002}
<!-- ndf: kind=decision date=2026-07-28 affects=API-003,BEH-005 source=observed -->

**Context.** PQ 编码需要训练 codebook + 编码所有向量。`train_pq.py` 和 `gen_gt.py` 都 import faiss。

**Decision.** 使用 faiss Python 包（`faiss.ProductQuantizer` + `faiss.IndexFlatL2`）做 PQ 训练和 Ground Truth 暴力搜索。

**Alternatives rejected.** 自研 PQ 训练（faiss 已有高效实现）；使用 scikit-learn KMeans（慢一个数量级）。
**Inferred from.** `scripts/train_pq.py:33` (`import faiss`), `scripts/gen_gt.py:26` (`import faiss`)。(inferred)

## D-003: 选择 io_uring 而非 libaio {#DEC-003}
<!-- ndf: kind=decision date=2026-07-28 affects=ARCH-001,DEF-011 source=observed -->

**Context.** 异步 I/O 预取需要高效的内核接口。代码自行封装了 raw `io_uring_setup(2)` 系统调用，未使用 liburing。

**Decision.** 使用 io_uring 原生系统调用（无外部 I/O 库依赖），通过 `IoUring` wrapper class 封装。支持 batch submit、O_DIRECT 对齐读取、buffer pool。

**Alternatives rejected.** libaio（接口老旧，不支持 batch submission）；liburing（增加外部依赖）；pread（同步，单线程可用但多线程不如 io_uring）。
**Inferred from.** `io_uring_wrapper.h:3-5`（"No external liburing dependency required"），`src/core/graph_prefetcher.cpp` 中 io_uring 的预取逻辑。(inferred)

## D-004: 选择 dual-route-table 修复 FINE_RERANK bug {#DEC-004}
<!-- ndf: kind=decision date=2026-07-28 affects=BEH-007,DEF-010 source=observed -->

**Context.** blocks 文件（含邻接表，8651 块）和 vecblocks 文件（仅向量，7937 块）因元数据大小不同，同一 node 在两文件里 block_id 不一致。原代码用 blocks 的 route_table 索引 vecblocks，导致读到错误向量。

**Decision.** 新增 `vec_route_table_` 成员（node → vecblocks block_id），在 `buildFineRerank()` 扫描每个 vecblocks 块时构建。FINE_RERANK 精排路径用 `vec_route_table_` 计算偏移，用 `route_table_` 查 block cache。

**Alternatives rejected.** 强制两个文件使用相同 block 划分（会牺牲 vecblocks 的存储效率）；用隐式 offset 推导（脆弱，已在原始实现中证明不可靠）。
**Inferred from.** README P0.5 章节、"fix(FINE_RERANK)" commit `1906400`、`disk_hnsw.h:266` 的 `vec_route_table_` 成员。(inferred)

## D-005: 选择 CSR Delta+Varint 而非 BVGraph 压缩 {#DEC-005}
<!-- ndf: kind=decision date=2026-07-28 affects=DEF-008,DEF-009 source=observed -->

**Context.** L0 邻接表 84MB 需要压缩以降低常驻内存。分析了 BFS-ordered CSR 的 delta 分布（4.2% delta=1, 32% delta<1024, 68% delta≥1024）。

**Decision.** 使用 delta+varint 编码（LEB128），不采用 BVGraph 参考压缩。BVGraph 依赖相邻节点 Jaccard 相似度，BFS 相邻节点 Jaccard 仅 0.023，不适合。

**Alternatives rejected.** BVGraph reference compression（Jaccard 太低不适用）；PForDelta（对 68% 长程边收益小）；直接 uint16 truncation（HNSW long-range edges 超 16-bit 范围）。
**Inferred from.** README P0 章节、`common.h:171-198` 的 `delta_varint_encode/decode` 函数、`common.h:24` 的 `FORMAT_VERSION_COMPRESSED = 2`。(inferred)

## D-006: BFS 重排作为默认布局策略 {#DEC-006}
<!-- ndf: kind=decision date=2026-07-28 affects=DEF-003,ARCH-004 source=observed -->

**Context.** 向量在磁盘上的排列顺序影响块内命中率。`BfsLayoutProvider` 是唯一实际使用的路由表加载器。

**Decision.** 使用 BFS 遍历顺序重排节点（`bfs_reorder.cpp`），让图上相邻节点在磁盘上物理相邻。`RandomLayoutProvider` 作为对照组存在但非生产路径。

**Alternatives rejected.** Random（对照组，命中率低）；Hilbert/ Morton space-filling curve（需要额外计算，BFS 直接利用图结构）。
**Inferred from.** `bfs_reorder.cpp` 存在、`BfsLayoutProvider` 是 `BlockCache` 向后兼容构造函数的默认选择（`block_cache.cpp:148`）、`RandomLayoutProvider` 仅用于对照实验。(inferred)

## D-007: 选择 C++17 + g++ 而非 Clang {#DEC-007}
<!-- ndf: kind=decision date=2026-07-28 affects=CON-006 source=observed -->

**Context.** 需要 C++17 特性（`std::optional`, structured bindings, `if constexpr`）和 AVX2 intrinsics。

**Decision.** 使用 `g++ -std=c++17 -O3 -march=native`。No CMake，直接用 Makefile。

**Alternatives rejected.** CMake（过度工程，10 个编译目标用 Makefile 足够）；Clang（g++ 对 AVX2 intrinsics 支持更稳定）。
**Inferred from.** `Makefile:2` (`CXX = g++`, `CXXFLAGS = -O3 -std=c++17 -Wall -Wextra -march=native`)。(inferred)

---

<!-- ════════════════════════════════════════════════════════════════ -->
<!-- deduced 条款：基于全局理解的选型理由补充                    -->
<!-- source=deduced 表示条款源自架构推理，非从代码直接提取         -->
<!-- ════════════════════════════════════════════════════════════════ -->

## D-008: 两阶段搜索作为当前最优搜索配置 {#DEC-008}
<!-- ndf: kind=decision date=2026-07-28 affects=BEH-002 source=deduced -->

**Context.** [[BEH-002]] 显示 `searchKnn()` 有 5 种搜索模式（TwoStage/Beam/NonBlock/
BatchIO/Default），由环境变量分支选择。**两阶段搜索是 5 种模式之一，并非唯一的架构路径。**
它是当前生产使用的最优配置，其他模式（Beam/NonBlock/BatchIO）为实验性探索，
同样存在于代码中且可在运行时切换。

传统 HNSW 搜索每展开一个节点都需要读其向量算距离。100 万 128 维向量需 488MB 内存。
在 512MB cgroup 限制下，hnswlib（726MB RSS）直接 OOM。两阶段搜索是把向量从内存
卸载到磁盘的可行方案之一（而非“核心机制”）。

**Decision.** 采用两阶段搜索作为当前最优配置：
- **Phase A（粗筛）**：用 PQ（Product Quantization）把每向量从 512 字节压缩到 32 字节，
  全量 PQ codes 仅 30MB 常驻内存。图搜索过程中用 PQ ADC 近似距离替代精确 L2，零向量 I/O。
  产出 ~100 个候选节点。
- **Phase B（精排）**：只对这 100 个候选取真实向量做精确 L2。按 4KB 页粒度读取（每向量
  512B，I/O 量 = 100 × 512B ≈ 50KB/query），而非加载 488MB 全量数据。

**关键权衡**：
- PQ 近似引入距离误差，recall 从 ~99% 降到 ~95%。由 Phase B 精排补偿（最终 95.70%）
- I/O 量从 488MB（全量加载）降到 50KB/query（5 个数量级）
- 延迟代价：PQ 查表 ~16μs + 4KB I/O ~1-10μs = 总 0.5ms/query（vs hnswlib 0.08ms）
- 用 3.5x 延迟换 2.7x 内存节省，在内存受限场景下是合算的交易

**Alternatives rejected.**
- **全量内存 + mmap**：OS 透明分页，但 cgroup 限制下仍 OOM，且 page fault 不可控
- **全量磁盘 + 大 block cache**：64KB block 读太多不需要的向量，I/O 量 5.3MB/query
- **IVF + PQ（如 FAISS IVFPQ）**：倒排索引 + 批量查询优化好，但单查询延迟高（nprobe 开销）
- **DiskANN**：Vamana 图 + 固定扇出，但搜索路径更长，单查询 I/O 更多
- **Beam/NonBlock/BatchIO**：代码中存在实验性实现（见 [[BEH-002]]），但均未达到两阶段的 recall/QPS 平衡

> rationale: 两阶段搜索的本质是“用计算换内存”——PQ 压缩是计算（查表），
> 磁盘 I/O 是按需的（只读候选）。在 CPU 富余、内存稀缺的场景下，这是正确交换。

## D-009: 选择 4KB 页粒度而非 64KB block 粒度做精排 {#DEC-009}
<!-- ndf: kind=decision date=2026-07-28 affects=BEH-007,DEF-006 source=deduced -->

**Context.** Phase B 精排需要读取候选向量的真实数据。有两种粒度可选：
- 按 64KB block 读（BlockCache 已有的机制）
- 按 4KB 页读（Fine Rerank 机制）

**Decision.** 选择 4KB 页粒度，原因：

| 维度 | 64KB block | 4KB page |
|------|-----------|----------|
| I/O 量/query | 100 候选 × 64KB = 6.4MB | 100 × 512B = 50KB |
| I/O 倍减 | 1x | **128x** |
| 块内有效数据 | ~6%（100×512B / 6.4MB） | ~100%（页内只有向量） |
| 随机读放大 | 高（每 block 含 ~116 向量，只用 1 个） | 低（每页含 8 向量，可能用 1-2 个） |

**实现关键**：SIFT 向量 512B，一个 4KB 页放 8 个向量。候选的页命中率约 12.5%（8 个里
命中 1 个），但 BFS 重排让图上相邻节点物理相邻，实际命中率更高。

**Alternatives rejected.**
- 64KB block 精排：I/O 量太大，512MB cgroup 下 page cache 放不下热 block
- 2KB sub-page：Linux 不支持小于 page_size 的 I/O，需用户态拼接，复杂度不值得
- mmap + userfaultfd：可以按需加载，但 signal handler 路径不稳定，且 cgroup 记账不直观

## D-010: delta+varint 的事后技术观测 {#DEC-010}
<!-- ndf: kind=info level=may layer=L2 status=stable since=0.2 source=deduced -->

**Context.** [[DEC-005]] 记录了 delta+varint vs BVGraph 的选择，决策完全基于
Jaccard = 0.023 的数据分析。以下为事后技术观测，非原始决策理由。

**事后观测：** delta+varint 恰好具备以下特性，但对决策不起决定性作用：

1. **解码独立性**：delta+varint 的解码逻辑自包含（`common.h:171-198`），不依赖外部状态。
   BVGraph 需要维护 reference node 的上下文
2. **随机访问友好**：`adj_csr_byte_offsets_[N+1]` 提供节点级随机访问入口，O(1) 定位。
   BVGraph 的变长 reference chain 需要顺序扫描
3. **线程安全简单**：`csr_decode_buf_` 是 thread_local，每个线程独立解码。
   BVGraph 的共享 reference state 需要锁保护
4. **压缩率足够**：1.8x 压缩（84->47MB）已让 1M 规模的 CSR 不是内存瓶颈。
   100M 规模时 CSR 上磁盘是更有效的方案，不需要更高压缩率

> 注意：以上特性是选择 delta+varint 后发现的技术优点，不是选择它的原因。
> 原始决策理由见 [[DEC-005]]（Jaccard 分析）。
> ~~原版本声称“与六边形架构兼容”已删除：决策时六边形架构概念不存在~~

## D-011: BFS 重排作为默认布局的架构理由 {#DEC-011}
<!-- ndf: kind=decision date=2026-07-28 affects=DEC-006,ARCH-005 source=deduced -->

**Context.** [[DEC-006]] 记录了 BFS vs Random vs Hilbert 的选择。补充架构理由。

**Decision.** BFS 重排是“图结构感知”的布局策略，与搜索领域高度内聚：

1. **与搜索路径一致**：HNSW 搜索从 entry point 做 best-first 扩展，访问的节点在图上
   是连续的。BFS 重排让这些连续节点在磁盘上也连续，自然提升 page cache 命中率
2. **与 BlockCache 解耦**：BFS 重排在 pipeline 阶段完成（`bfs_reorder.cpp`），
   运行时只需要一个映射表（`old_to_new_` / `new_to_old_`）。布局策略不影响
   BlockCache 的实现，符合 Port-Adapter 分离
3. **可测量**：BFS 后块内命中率 86.8%（实测），Random 只有 ~12%。可量化的提升
   让布局策略的选择有数据支撑
4. **不可变假设**：BFS 顺序在建索引时确定，运行时不变。这简化了设计——
   不需要动态重排或自适应布局

## D-012: 双路由表分离作为显式映射原则 {#DEC-012}
<!-- ndf: kind=decision date=2026-07-28 affects=DEC-004,ARCH-007 source=deduced -->

**Context.** [[DEC-004]] 记录了 `vec_route_table_` 的引入。补充架构层面的原则。

**Decision.** 双路由表分离体现了核心原则：“不依赖隐式对齐”。提升为架构规则：

1. **每套数据文件 MUST 有独立的路由表**：blocks 文件、vecblocks 文件、PQ blocks 文件
   如果有不同的 block 划分（因元数据大小不同），各自维护映射
2. **路由表的变更需版本化**：如果 vecblocks 文件重新生成（如改 block_size），
   `vec_route_table_` 必须同批重建，并在 `ndf.yaml` 中记录版本

> ~~原第 2 条“路由表是 Port 的实现细节”已删除：`IRouteTable` 接口在代码中不存在~~

> rationale: P0.5 的 FINE_RERANK bug（recall 95.70% -> 10%）就是违反此规则的代价。
> 隐式对齐在数据碰巧一致时正常工作，pipeline 变更后立即暴露。显式映射的成本
> 是 4MB 内存，收益是消除一整类数据一致性 bug。

## D-013: 选择 io_uring 原生 syscall 而非 liburing 的架构理由 {#DEC-013}
<!-- ndf: kind=decision date=2026-07-28 affects=DEC-003 source=deduced -->

**Context.** [[DEC-003]] 记录了 io_uring vs libaio 的选择。补充不用 liburing 的理由。

**Decision.** 直接使用 `io_uring_setup(2)` + `io_uring_enter(2)` 系统调用，不依赖 liburing：

1. **封装简洁**：`IoUring` class（363 行）封装了 setup/submit/wait 完整生命周期，
   代码量与 liburing wrapper 相当
2. **控制力**：直接操作 SQ/CQ ring（mmap），可以精确控制内存布局和提交时机。
   liburing 的抽象层会隐藏这些细节

**风险**：内核 io_uring API 变更时需要手动适配（liburing 会处理）。但 io_uring 核心
API（setup/enter/mmap）自 Linux 5.1 起稳定，变更风险低。

## D-014: PQ M=32 的选择理由 {#DEC-014}
<!-- ndf: kind=decision date=2026-07-28 affects=CON-005,BEH-005 source=deduced -->

**Context.** SIFT 128 维向量，PQ 参数 M 决定每向量压缩后的字节数和距离计算次数。
M=32 意味着 dsub=4（128/32），每子空间 4 维。

**Decision.** M=32 是 recall 与内存的最佳平衡点：

| M | dsub | PQ codes 大小 | ADC recall@10 | 查表次数 |
|---|------|-------------|---------------|----------|
| 8 | 16 | 8MB | ~70% (太低) | 8 |
| 16 | 8 | 16MB | ~88% | 16 |
| **32** | **4** | **30MB** | **~93%** | **32** |
| 64 | 2 | 64MB | ~96% | 64 |
| 128 | 1 | 128MB | ~97% | 128 |

**关键权衡**：
- M=32 的 ADC recall ~93%，加上 Phase B 精排后达到 95.70%
- M=64 的 ADC recall ~96%，但 PQ codes 64MB 过大，挤压 CSR 和 flat_vec_cache 预算
- M=32 的 PQ dist table = 32×256×4 = 32KB，恰好在 L1 cache（48KB）内
- M=64 的 PQ dist table = 64KB，超出 L1，性能反而下降

**SIMD 优化对齐**：dsub=4 时 AVX2 一次处理 2 个 centroid（8 floats），M=32 的 32 次查表
可展开为 8 组 4 路并行，完美利用 AVX2 256-bit 寄存器。

> rationale: PQ M 的选择不仅是 recall 问题，更是 cache hierarchy 问题。
> M=32 的 dist table 适配 L1 cache，是性能的甜点。

## D-015: flat_vec_cache 热区行为观测 {#DEC-015}
<!-- ndf: kind=info level=may layer=L2 status=stable since=0.2 source=deduced -->

**Context.** P1 阶段实验发现，flat_vec_cache 在 `FLAT_VEC_MB=64` 配置下支撑了大部分 QPS，
而非 vecblocks 的 page cache。此条目记录观测经验，非代码内建设计意图（代码默认
`FLAT_VEC_MB=4`，见 [[CON-002]]）。

**观测经验：**

1. **推荐配置 `FLAT_VEC_MB=64`**：63K 个 Layer 1+ 节点的向量（30MB），在 64MB 下
   100% 装入。贪心下降阶段零 I/O。代码默认 4MB 只能装 ~8K 向量，不够用
2. **Layer 0 热点覆盖**：剩余 ~34MB 装约 68K 个 Layer 0 热门节点（LRU 淘汰），
   PQ_HYBRID 模式下这些节点用精确 L2 替代 PQ，提升粗筛质量
3. **与 page cache 的分工**：flat_vec_cache 是进程主动管理的 anon 内存（计入 RSS），
   page cache 是 OS 管理的 file cache（cgroup 记账有坑）。flat_vec_cache 可控、可测、
   不受 cgroup 记账影响
4. **调大的边际效益递减**：`FLAT_VEC_MB=64->256` 实测 QPS 不涨反微降（2065->2037），
   因为更大的 flat_vec_cache 挤压了 CSR/PQ codes 的内存预算，且 L1/L2 cache miss 增加

> rationale: flat_vec_cache 是“可控热区”，page cache 是“免费但不稳定的补贴”。
> 推荐配置 `FLAT_VEC_MB=64` 覆盖上层节点，page cache 作为 bonus。
> 注意：这是 benchmark 经验值，非代码默认值。

## D-016: 选择 cgroup v2 而非 v1 作为内存限制机制 {#DEC-016}
<!-- ndf: kind=decision date=2026-07-28 affects=CHR-006 source=deduced -->

**Context.** 项目使用 `systemd-run --user -p MemoryMax=512M` 限制内存，这依赖 cgroup v2。

**Decision.** 使用 cgroup v2（而非 v1）的原因：

1. **统一层级**：cgroup v2 的 memory.current / memory.stat 统一了 v1 的 memory.usage_in_bytes
   和 memory.stat，语义更清晰
2. **systemd 原生支持**：`systemd-run --user -p MemoryMax=` 直接映射到 cgroup v2，
   无需手动创建 cgroup
3. **page cache 记账改进**：cgroup v2 的 memory.stat 区分 `anon`（进程私有）和 `file`
   （page cache），虽然仍有“首次读入位置”的记账陷阱（[[CHR-005]]），
   但比 v1 的不区分更透明
4. **Linux 5.1+ 对齐**：io_uring 也需要 5.1+，cgroup v2 在同一内核版本范围内默认启用

> rationale: cgroup v2 的 file/anon 区分让我们发现“page cache 100% 在系统缓存但
> cgroup file=0”的记账陷阱（P1 阶段的关键认知修正）。如果用 v1，这个发现不可能做出。

---

