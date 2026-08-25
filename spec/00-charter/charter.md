# DiskHNSW — Charter

> scope: product (00-charter)
> status: stable | perf: not-established | bootstrap: adopt
> Observed Trunk SHA: `d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755`

本文件承载产品**目标、范围、非目标**与核心术语。非 SLA 条款 `status=stable`
（skeleton = 优化对照目标）；性能数字须由 [[VER-001]] 协议产出后写入
`spec/50-verification/baselines/` 才可晋升为 stable SLA（SIFT1M sustained 已确立，
见 [[CON-SLA-001]]；其余场景 `not-established`）。

## 产品目标 {#CHR-001}
<!-- ndf: kind=req level=must layer=L0 status=stable since=0.1 source=observed -->

DiskHNSW MUST 在受约束内存预算（cgroup `memory.max`）下，对磁盘驻留的向量集合执行
近似最近邻（ANN）检索，达到与全内存 HNSW 相当的召回（目标 ≥95%），并以绝对内存占用
换取吞吐作为明确的 trade-off。

> rationale: 传统 HNSW 需将全部向量驻留内存（SIFT1M ~726MB、DEEP10M ~7GB），在容器化
> 与边缘计算等内存受限场景不可行。DiskHNSW 的定位是"内存预算不足时仍能工作"，而非
> 全面胜过全内存基线。见 [[CHR-003]]。

## 范围 {#CHR-002}
<!-- ndf: kind=req level=should layer=L0 status=stable since=0.1 source=observed -->

In-scope（由 observed Trunk `include/` 与 `src/` 推导）：

1. 磁盘驻留向量集合的 ANN 索引加载与检索（图结构常驻内存 + 向量按需 I/O）。
2. Product Quantization（PQ）粗筛 + 精确精排（Fine Rerank）两阶段搜索。
3. 块级缓存（BlockCache）、图引导预取（GraphPrefetcher）、页缓存管理（WILLNEED）等
   I/O 优化机制。
4. 跨架构 SIMD 抽象（x86 AVX2 / ARM NEON / 标量 fallback）。
5. 索引构建流水线（建图 → 提取 → BFS 重排 → 分块 → PQ 编码）。
6. 基准与回归测量（sustained 权威口径 + cache-warmed 回归护栏）。

## 非目标 {#CHR-003}
<!-- ndf: kind=req level=must layer=L0 status=stable since=0.1 source=observed -->

DiskHNSW MUST NOT 承诺：

1. 在无内存约束下超越全内存 HNSW 的吞吐（trade-off 而非全面胜出）。
2. 修改 / 插入 / 删除向量（当前为只读检索，索引离线构建）。
3. 分布式 / 多机检索。
4. 非欧氏距离度量（当前为 L2）。
5. 将 cache-warmed 口径数字冒充对外商用吞吐声明（见 [[DEC-002]]）。

## 成功判据 {#CHR-004}
<!-- ndf: kind=req level=should layer=L1 status=stable since=0.1 source=observed -->

产品在当前里程碑 SHALL 以以下条件判定成功（SIFT1M 已确立、DEEP10M 待测；无证据不设 must）：

1. SIFT1M（128 维 / 1M 向量）在 ≤512MB cgroup 下，sustained 口径 recall ≥95%。
2. DEEP10M（96 维 / 10M 向量）在 ≤2GB cgroup 下可运行（全内存 hnswlib 直接 OOM）。
3. 结果可复现：绑定 Trunk SHA × 配置身份 × 测量数字（[[VER-004]]、[[VER-005]]）。

> rationale: 数字仅在测量证据落地后晋升为 stable SLA（[[CON-SLA-001]] 起）。

## 术语 {#DEF-001}
<!-- ndf: kind=def level=must layer=L0 status=stable since=0.1 source=observed -->

- **DiskHNSW**：内存受限场景下的磁盘驻留 HNSW 检索器（[[API-001]]）。
- **Block**：BFS 重排后按固定大小（默认 256KB）分块的向量容器，磁盘上按需读取的粒度。
- **BFS reorder**：对图节点做广度优先重排，使相邻节点落于连续 block，提升空间局部性；
  产生 `old_id`（hnswlib 内部）↔ `new_id`（BFS 重排后）映射。
- **PQ（Product Quantization）**：将向量压缩为子量化器码本索引，常驻内存用于零 I/O 近似距离。
- **Fine Rerank**：对 PQ 粗筛候选按 4KB 页粒度读取真实向量，做精确 L2 重排得到 top-K。
- **sustained 口径**：官方 10K query 池、多轮随机采样、禁止预热被测 query 的测量方式
  （[[DEC-002]]、[[VER-001]]）。
- **cache-warmed 口径**：计时前将全部 query 跑一遍预热 page cache 的测量方式，高估
  1.73–7.60×，仅作回归护栏（[[DEC-002]]、[[VER-002]]）。
- **cgroup memory budget**：容器 cgroup `memory.max` 施加的进程内存上限，DiskHNSW 的
  核心运行约束（[[CON-001]]）。

> 以上术语的详细机制见 `spec/10-architecture/architecture.md`。
