# Glossary — 术语定义

## DEF: GraphStructure {#DEF-001}
<!-- ndf: kind=def layer=L1 status=stable since=0.1 source=observed -->

HNSW 图的内存表示。定义于 `common.h:113-136`，包含：
- `num_nodes`, `dim`, `maxM`, `maxM0`: 图元数据
- `levels[n]`: 每个节点的最高层
- `vectors[n*dim]`: 全量向量（slim 模式下不加载）
- `labels[n]`: uint64 外部标识
- `adjacency0[n]`: L0 邻接表（slim 模式下不加载）
- `upper_adjacency[n][level]`: 上层邻接表

## DEF: slim 加载模式 {#DEF-002}
<!-- ndf: kind=def layer=L2 status=stable since=0.1 source=observed -->

`load_graph_structure_slim()` 和 `load_graph_structure_slim_adj()` 只加载上层节点向量和 L0 邻接表，跳过全量 L0 向量。RSS 从 ~584MB 降至 ~52MB（无邻接表）或 ~133MB（含邻接表）。

## DEF: BFS 重排 {#DEF-003}
<!-- ndf: kind=def layer=L2 status=stable since=0.1 source=observed -->

按图的 BFS 遍历顺序给节点重新编号，让相邻节点在磁盘块中物理相邻，提升块内命中率。通过 `old_to_new_` / `new_to_old_` 双向映射表维护新旧 ID 关系。

## DEF: Two-Stage Search {#DEF-004}
<!-- ndf: kind=def layer=L1 status=stable since=0.1 source=observed -->

两阶段搜索 = Phase A (PQ ADC 粗筛，零向量 I/O) + Phase B (精确 L2 精排，4KB 页粒度按需读)。环境变量 `TWO_STAGE=1` 启用。

## DEF: PQ (Product Quantization) {#DEF-005}
<!-- ndf: kind=def layer=L2 status=stable since=0.1 source=observed -->

将 d 维向量空间分解为 M 个 dsub 维子空间，每个子空间用 ksub=256 个中心点量化。编码后每向量 M 字节。存储在 `pq_codes_[]` 中，按 BFS new_id 索引。

## DEF: Fine Rerank {#DEF-006}
<!-- ndf: kind=def layer=L2 status=stable since=0.1 source=observed -->

Phase B 精确精排：对 Phase A 粗筛的候选（约 100 个），按 4KB 页粒度读取真实向量做精确 L2 距离重排。通过 `FINE_RERANK=1` 开启，依赖 `VEC_BLOCKS_PATH`。

## DEF: Block/VecBlock {#DEF-007}
<!-- ndf: kind=def layer=L2 status=stable since=0.1 source=observed -->

- **Block**: 64KB/256KB 磁盘块，含邻接表 + 向量（`write_blocks` 产出），供 BlockCache 使用
- **VecBlock**: 仅含向量的 64KB 块（`write_blocks_veconly` 产出），供 Fine Rerank 4KB 页粒度读取

## DEF: CSR (Compressed Sparse Row) {#DEF-008}
<!-- ndf: kind=def layer=L2 status=stable since=0.1 source=observed -->

邻接表存储格式。`adj_csr_offsets_[N+1]` + `adj_csr_neighbors_[total_edges]`。P0 优化后支持 delta+varint 压缩（`adj_csr_compact_` 字节流 + `adj_csr_byte_offsets_`）。

## DEF: Varint Encoding {#DEF-009}
<!-- ndf: kind=def layer=L2 status=stable since=0.1 source=observed -->

LEB128 无符号整数变长编码 (`common.h:143-167`)。Delta+Varint 组合：先对排序后的邻居 ID 做 delta 编码（存差值），再用 varint 编码差值。4 字节 uint32 可压至 1-5 字节。

## DEF: Route Table {#DEF-010}
<!-- ndf: kind=def layer=L2 status=stable since=0.1 source=observed -->

`node_id -> block_id` 映射表（`route_table_`）。存在两个变体：
- `route_table_`: blocks 文件的路由（用于 BlockCache 查询）
- `vec_route_table_`: vecblocks 文件的路由（专用于 Fine Rerank），修复了 blocks/vecblocks block_id 不一致的 bug

## DEF: io_uring {#DEF-011}
<!-- ndf: kind=def layer=L2 status=stable since=0.1 source=observed -->

Linux 5.1+ 内核异步 I/O 接口。`IoUring` 类 (`io_uring_wrapper.h`) 通过 `io_uring_setup(2)` + `mmap` SQ/CQ ring + `io_uring_enter(2)` 实现零外部依赖的异步 I/O。

## DEF: Page Search {#DEF-012}
<!-- ndf: kind=def layer=L1 status=stable since=0.2 source=deduced -->

Fine Rerank 的 opt-in 扩展：读取每个 4KB 页后，扫描页内全部向量做精确 L2（不仅候选）。由 `PAGE_SEARCH=1` 开启；契约见 [[BEH-014]]，SLA 豁免见 [[CON-SLA-008]]。

## DEF: Dynamic Width {#DEF-013}
<!-- ndf: kind=def layer=L1 status=deprecated since=0.2 source=deduced -->

Phase A 自适应 efSearch：收敛后几何衰减宽度。由 `DYNAMIC_WIDTH=1` 开启。[[DEC-024]] 已正式放弃（PQ 粗筛不收敛）；见 [[BEH-015]]（deprecated）。

## DEF: FINE_DIRECT {#DEF-014}
<!-- ndf: kind=def layer=L1 status=stable since=0.4 source=deduced -->
<!-- ndf: depends-on=DEC-059 -->

环境变量 / 打开模式：`FINE_DIRECT=1` 时 vecblocks 以 `O_DIRECT` 读取，绕过 OS page cache。
定位为**性能地板与优化基座**（[[DEC-059]]），并用于诚实基准的 Direct 组（[[CON-HONEST-002]]）。
默认生产打开仍可为 Buffered；大规模 / 预算耗尽时 O_DIRECT 是多数查询的真实路径。
（旧「诊断/测试模式」叙事见已 superseded 的 [[DEC-030]]。）

## DEF: Honest I/O {#DEF-015}
<!-- ndf: kind=def layer=L1 status=stable since=0.4 source=deduced -->

诚实测量协议：基准 MUST 报告 Buffered（`FINE_BUFFERED=1`）与 Direct（`FINE_DIRECT=1`）两组数据，或明确标注单模式局限。契约 [[CON-HONEST-002]]；决策 [[DEC-039]]；下限 [[CON-SLA-011]]。

## DEF: cgroup MemoryMax {#DEF-016}
<!-- ndf: kind=def layer=L1 status=stable since=0.2 source=deduced -->

Linux cgroup v2 的 `memory.max`：同时限制匿名内存与 page cache（file）。DiskHNSW 部署与基准 MUST 在给定 MemoryMax 下运行；Buffered 模式的 page cache 计入同一预算（见 [[CON-HONEST-002]]）。

## DEF: O_DIRECT 地板优化 {#DEF-017}
<!-- ndf: kind=def layer=L1 status=stable since=0.6 source=deduced -->

O_DIRECT 模式下的真实磁盘 I/O 性能是 DiskHNSW 的性能地板（[[DEC-059]]）。优化目标是减少 I/O 次数、增大粒度、批量化、I/O 与计算重叠，以抬高无缓存时的 QPS 地板。具体方案见 [[DEC-060]]。

## DEF: Page Cache 受限加速 {#DEF-018}
<!-- ndf: kind=def layer=L1 status=stable since=0.6 source=deduced -->

在 cgroup 预算内（`memory.max ≥ RSS + page_cache`）自然填充 page cache，热数据自动被缓存。可用预算 = cgroup_limit - RSS，随数据规模增大对 vecblocks 的覆盖率趋近于 0。Page cache 是有限加成，不是性能基座（[[DEC-059]]）。

## DEF: Read Coalescing (已废弃) {#DEF-019}
<!-- ndf: kind=def layer=L1 status=deprecated since=0.6 source=deduced -->

> **Deprecated (2026-07-31):** v1 pread +6-9%，v2 io_uring -10~16%，代码已回退。见 [[DEC-061]]。

Fine Rerank 候选页按 coalesce block（默认 64KB）分组：密集 block 一次大读，稀疏仍 4KB。
由 `READ_COALESCE=1` 开启；环境变量不再生效。

## DEF: POC（概念验证） {#DEF-020}
<!-- ndf: kind=def layer=L1 status=stable since=0.7 source=deduced -->

针对单一探索主题（通常对应一个 `proposal-*` / DEC 方向）的**可丢弃**实现与测量集合。
POC 的目标是产生证据（正/负），不是扩展生产 API 表面。承载面见 [[ARCH-008]]；纪律见 [[BEH-018]]。

## DEF: 晋升（Promote） {#DEF-021}
<!-- ndf: kind=def layer=L1 status=stable since=0.7 source=deduced -->

将 POC 中**已证实有效**的最小变更集，经提案确认后写入固定目录（stable 契约）并合入 `src/`
的过程。晋升 MUST 可追溯到证据与 DEC/提案 ID。闸门见 [[BEH-019]]。

## DEF: Topic Binder（主题装订器） {#DEF-022}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced -->
<!-- ndf: depends-on=DEF-020,ARCH-008,BEH-025 -->

某一 `poc/<topic>/` 探索主题的**进度与可复现入口**，目录为 `poc/<topic>/ndf/`
（含 `TOPIC.md`、`proposals/`、`evidence/`、`COMMITS.md`）。装订器 **不是** Trunk SoT
（`poc.sot: false`）；Trunk must 仍只在 `spec/00–50`。纪律见 [[BEH-025]]。

## DEF: Commit Ledger（提交账本） {#DEF-023}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced -->
<!-- ndf: depends-on=DEF-022,BEH-025 -->

`poc/<topic>/ndf/COMMITS.md` 中的对照表：将 `code_commit` 与（可选）`ndf_commit`、
提案 ID、条款 ID、验证协议绑定，使仅凭装订器即可定位如何复现该提交的测量结果。
