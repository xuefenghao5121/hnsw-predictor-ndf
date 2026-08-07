# TOPIC: csr-on-disk

> topic_id: csr-on-disk
> status: exploring
> baseline_protocol: [[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]] (sustained)
> baseline_trunk_sha: 8520366
> baseline_status: current
> explore_surface: graph-structure,io-path,memory-layout
> depends_on_topics: sustained-query-benchmark (promoted), l4-cache-mgmt (promoted)
> conflicts_with_topics: []
> binder: [[DEF-022]]
> opened: 2026-08-07

## 目标

将 L0 CSR 压缩邻接表从内存移到磁盘，通过 page cache 按需加载，
压缩 RSS（SIFT1M: -47MB, DEEP10M: -470MB, 100M: -4.7GB），验证性能影响。

## 背景

CSR compact（delta+varint 压缩邻接表）占 init RSS 的 30%（SIFT1M 47MB / 157MB）。
100M 规模下将达 4.7GB，是内存瓶颈（[[DEC-010]]、[[DEC-037]]）。

BFS 重排（[[DEC-006]]）使图相邻节点在 CSR 文件中物理相邻，
4KB page 可容纳 ~83 个 CSR entries，为 page cache 提供天然局部性。

调研见 `spec/open/proposal-csr-on-disk.md`。

## Active hypothesis

CSR 上磁盘后，BFS 重排提供的空间局部性使 page cache 命中率足够高，
sustained QPS 下降 < 30%，RSS 下降 ≥ 40MB（SIFT1M）。

## 方案

递进验证三种 I/O 路径：
1. **方案 A (mmap)**: 最简实现，内核管理 page cache，MADV_RANDOM
2. **方案 C (mmap + WILLNEED 预取)**: 复用 WILLNEED_BG SPSC 架构
3. **方案 B (分页 BlockCache)**: 显式控制，复用 LRU 基础设施

保留在内存：byte_offsets（3.8MB, 随机访问索引）、上层图+向量、PQ codes。
移到磁盘：adj_csr_compact_（压缩邻接表字节流）。

## 实验计划

| 轮次 | 内容 | 验收 |
|------|------|------|
| R0 | mmap 基线 (SIFT1M 512/256MB sustained) | recall 不变; QPS 下降量化 |
| R1 | 性能分析 (mincore, majfault, I/O 量) | 瓶颈定位 |
| R2 | mmap + WILLNEED 预取 | QPS 恢复至 R0 的 90%+ |
| R3 | 256MB 极限内存验证 | QPS ≥ baseline 70% |
| R4 | DEEP10M 验证 (如时间允许) | RSS 显著下降 |

## 晋升条件

1. recall ≥ 95% (sustained, 不变)
2. QPS 下降 < 30% (512MB, vs CSR in-mem baseline)
3. RSS 下降 ≥ 40MB (SIFT1M)
4. 256MB cgroup 下可工作

## Draft clauses

| ID (draft) | 说明 |
|------------|------|
| BEH-036 (draft) | L0 CSR 邻接表磁盘驻留 |
| API-020 (draft) | CSR_FILE_PATH 环境变量 |

## 写入边界

- 本 POC MUST NOT 修改 Trunk `src/`（[[BEH-018]] 第 6 条）
- 所有实现在 `poc/csr-on-disk/`
- draft 条款只落 `poc/csr-on-disk/ndf/proposals/`

## 表面冲突检查

无活跃 exploring 主题。已 promoted 主题（l4-cache-mgmt, sustained-query-benchmark,
multi-thread-scaling）与本主题为叠加/依赖关系，不冲突。
