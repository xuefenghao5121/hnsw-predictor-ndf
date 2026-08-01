# Charter - 系统目标与范围

## 系统目标 {#CHR-001}
<!-- ndf: kind=arch level=must layer=L0 status=stable since=0.1 source=observed -->
<!-- ndf: depends-on=DEC-059,DEC-062 -->

DiskHNSW MUST 在 cgroup 内存限额(≥512MB)下,使用磁盘驻留向量数据,实现与全内存 HNSW 可比的向量搜索召回率(≥95%),同时将常驻内存控制在限额内。

cgroup v2 `memory.max` MUST 同时约束匿名内存与 page cache（file）；可用 page cache
预算 = limit − RSS。

**优化主目标（[[DEC-062]]）**：Buffered 模式（生产默认，`FINE_BUFFERED=1`）是性能优化的
主要目标。目标是在诚实 cgroup 预算下逼近 hnswlib 全内存方案性能。page cache 在预算内
是合法的核心加速层。

**诚实验收地板**：O_DIRECT（`FINE_DIRECT=1`）是无 page cache 补贴时的性能地板，以及
大规模下必然磁盘 I/O 的独立优化路径。两者各有独立优化空间，不假设 O_DIRECT 优化成果
会自然惠及 Buffered。双层策略见 [[DEC-059]]（经 [[DEC-062]] 修正优先级叙事）；
工程路线图见 [[DEC-060]]。

**核心业务实体(从代码强行归纳):**

1. **HNSW 图结构** (`GraphStructure` - `common.h:113-136`): 分层图,包含节点层级、向量、标签、邻接表,搜索时通过贪心下降 + best-first 遍历
2. **BlockCache** (`BlockCache` - `block_cache.h:116-430`): LRU 缓存的磁盘块管理器,按需加载 64KB/256KB 块,可插拔布局和替换策略
3. **PQ 编码** (`PQParams` + `pq_codes_` - `disk_hnsw.h:37-43`): Product Quantization 将 128 维向量压缩为 32 字节,用于 Phase A 零 I/O 粗筛
4. **两层搜索**: Phase A (PQ ADC 粗筛) + Phase B (精确 L2 精排),精排通过 4KB 页粒度 I/O 读取候选向量
5. **数据 Pipeline**: build_index → extract_graph → bfs_reorder → write_blocks → write_blocks_veconly → train_pq → gen_gt
6. **io_uring 异步 I/O** (`IoUring` - `io_uring_wrapper.h:57-363`): 内核异步 I/O,批量提交,O_DIRECT 对齐

## Scope {#CHR-002}
<!-- ndf: kind=arch level=L0 layer=L0 status=stable since=0.1 source=observed -->

- **IN**: 向量搜索(L2 距离)、PQ 训练与编码、BFS 重排优化块局部性、CSR 邻接表压缩、图引导预取、多线程并发搜索
- **IN**: cgroup 内存受限部署、数据 pipeline 工具链(build_index/extract_graph/bfs_reorder/write_blocks/write_blocks_veconly/gen_route/verify)
- **IN**: 可插拔缓存架构(LayoutProvider 接口 + ReplacementPolicy 接口)
- **OUT**: 增量插入/删除(当前只读搜索,无 insert/delete API)
- **OUT**: 多租户 QoS、分布式部署、持久内存支持
- **OUT**: GPU 加速(规划在 P5 阶段)

## Non-Goals {#CHR-003}
<!-- ndf: kind=info layer=L0 status=stable since=0.1 source=observed -->

- **不是**通用向量数据库:无 CRUD、无持久化日志、无 WAL
- **不是**实时插入系统:索引构建是离线 batch 操作
- **不是**跨平台方案:依赖 Linux 5.1+ (io_uring)、x86 AVX2、C++17

---

<!-- ════════════════════════════════════════════════════════════════ -->
<!-- deduced 条款:基于 README、代码结构和性能数据的推断性规范   -->
<!-- source=deduced 表示条款源自全局理解,非从单一代码实体提取 -->
<!-- ════════════════════════════════════════════════════════════════ -->
<!-- 原 CHR 用户/部署意图条款已删除（裁决：文档意淫，无部署/用户数据支撑） -->
<!-- ════════════════════════════════════════════════════════════════ -->

## 关键性能承诺 {#CHR-006}
<!-- ndf: kind=constraint level=must layer=L0 status=stable since=0.2 source=deduced -->
<!-- ndf: depends-on=CON-HONEST-002,CON-SLA-011,DEC-059,DEC-062 -->

DiskHNSW 对 SIFT1M(128 维,100 万向量)MUST 达成以下指标。QPS MUST 按 I/O 模式分行报告（见 [[CON-HONEST-002]]）。

**SoT：** 默认生产打开 Buffered（`FINE_BUFFERED=1`）；**优化主目标**为 Buffered（逼近
hnswlib，见 [[CHR-001]] / [[DEC-062]]）。**诚实验收地板**以 O_DIRECT（`FINE_DIRECT=1`）
为准。双层策略与 I/O 优化路线图见 [[DEC-059]] / [[DEC-060]] / [[DEC-062]]
（非本条款 must 数字）。

### Buffered（`FINE_BUFFERED=1`，生产默认）

| 指标 | 值 | 条件 | 验证方式 |
|------|-----|------|----------|
| Recall@10 | ≥ 95% | 512MB cgroup | benchmark vs GT |
| QPS (单线程) | ≥ 2000 | 512MB cgroup, CSR 压缩后 | benchmark |
| QPS (4 线程) | ≥ 5000 | 512MB cgroup | benchmark |
| RSS | ≤ 300MB | 512MB cgroup | /proc/self/status |
| 内存节省 | ≥ 2.5x | vs hnswlib 726MB | 对比测试 |

Buffered 模式下 page cache 与匿名内存共享 cgroup 预算，运行过程中峰值内存（anon + file）MUST NOT 超过 cgroup 限制。

### Honest / O_DIRECT（`FINE_DIRECT=1`，性能地板）

| 指标 | 值 | 条件 | 验证方式 |
|------|-----|------|----------|
| Recall@10 | ≥ 95% | 512MB cgroup | benchmark vs GT |
| QPS (单线程) | ≥ 100 | 512MB cgroup（实测 2026-07-31: 130） | benchmark |
| QPS (4 线程) | ≥ 400 | 512MB cgroup（实测 2026-07-31: 502） | benchmark |
| RSS | ≤ 300MB | 512MB cgroup | /proc/self/status |

仅报告 Buffered 数字时 MUST 附带声明：page cache 与匿名内存共享 cgroup 预算（[[CON-HONEST-002]]）。

> rationale: 95% recall 是生产可接受的最低召回率阈值;
> Buffered 2000 QPS 是交互式可用阈值; Honest 下限锚定 O_DIRECT 实测，消除无模式 QPS 双重真相。
> 抬高 O_DIRECT 地板的 aspirational 目标不属于本 must 条款，见 [[DEC-060]]。

## 演进路线意图（探索性设想） {#CHR-004}
<!-- ndf: kind=arch level=may layer=L0 status=draft since=0.2 source=deduced -->

> ⚠️ **探索性设想标签**：本条款无设计文档或代码支撑，仅为方向性思考。
> P0-P2 已完成并验证；P3-P5 为未落地的规划构想，不构成规范性承诺。

DiskHNSW 的设计意图是**从 1M 验证走向 100M 生产**：

- **P0-P1（已完成 ✅）**：1M 规模下验证内存卸载 + 压缩 + 图裁剪的可行性与边界
- **P2（已完成 ✅, 2026-07-30）**：10M 规模验证。DEEP10M 95.15% recall / 2340 QPS (12T) / 2GB cgroup。
  hnswlib 需 ~6GB OOM@2GB，DiskHNSW 3.7x 内存节省。
  瓶颈从 I/O 转移到 PQ 计算 (80%)，VisitedList 优化带来 2x QPS。
  1GB cgroup 物理不可行 (核心数据 1.3GB)，最小可行 1.8GB。
- **P3（进行中）**：多层内存优化 + 大规模验证（战略见 [[DEC-059]]，
  路线图见 [[DEC-060]]）。Buffered 模式逼近 hnswlib 性能为主要目标；
  O_DIRECT 地板优化为辅助路径。多层策略：L4 page cache 预算管理 +
  L5 pipe_ring_ I/O 重叠 + L1/L2/L3 CPU cache 计算加速。
  aspirational QPS 目标不构成本条款 must。
- **P4-P5（探索性构想）**：分级存储、硬件亲和（NUMA/SPDK/GPU/PMEM）。这些方向当前
  无代码或设计支撑，仅为探索性路线设想

每个阶段的核心验证：**"给定内存预算 M，DiskHNSW 能跑多大规模的向量搜索？"**
关键约束：RSS + page_cache ≤ M（cgroup v2 memory.max 同时限制匿名内存和 file cache）。

> rationale: 1M 规模下宿主机 page cache 能装下全部 496MB 向量数据，
> 掩盖了磁盘 I/O 优化的真实价值。10M 规模验证了瓶颈转移 (I/O -> PQ 计算)。
> 100M 规模 CSR 内存将成为新瓶颈，需要新的架构决策。

## 设计约束(推断) {#CHR-005}
<!-- ndf: kind=constraint level=should layer=L0 status=stable since=0.2 source=deduced -->

除 [[CHR-007]] 的硬约束外,以下软约束指导设计决策:

1. ~~**零外部运行时依赖**~~（已删除：裁决--伪约束，非主动设计，是 hnswlib header-only 特性的副产物）
2. **Linux 优先**:不追求跨平台,利用 io_uring、O_DIRECT、cgroup v2 等 Linux 特有能力
3. **C++17 而非 C++20**:保持与主流编译器的兼容性,避免 C++20 coroutine/modules 的编译器差异
4. **离线索引构建**:搜索是在线路径,索引构建是离线 batch。不追求在线插入性能
5. **可测量性**:每个优化 SHOULD 有 benchmark 数据支撑。未达预期的优化（如 `FINE_MERGE`、`SPEC_PREFETCH`）默认关闭并记录原因。这是理想目标而非强制纪律--代码中无机制阻止无 benchmark 的合入

## 设计约束 {#CHR-007}
<!-- ndf: kind=constraint level=must layer=L0 status=stable since=0.1 source=observed -->

1. 常驻内存 MUST ≤ cgroup MemoryMax(典型 512MB)
2. 搜索召回率 MUST ≥ 95% (Recall@10 on SIFT1M)
3. 所有数据准备步骤 MUST 用同一套 base 数据(graph/PQ/GT 共享 node id 空间)
4. vecblocks 与 route table MUST 配套生成,不可跨版本混用

## 探索与晋升双轨 {#CHR-008}
<!-- ndf: kind=arch level=must layer=L0 status=stable since=0.7 source=deduced -->
<!-- ndf: depends-on=BEH-018,BEH-019,BEH-020,ARCH-008 -->

DiskHNSW 的规范与代码演进 MUST 区分：

1. **探索轨（POC）**：验证某优化/机制是否成立；允许失败与回退（[[DEF-020]]）。
2. **主线轨（Trunk）**：已证明有效、纳入产品行为与 SLA 的实现（[[DEF-021]]）。

探索轨产物 MUST NOT 被默认当作 Trunk SoT；负结果 MUST 以决策记录关闭，不得靠
「静默删条款却留主线代码」或「删代码却留 stable must」维持表面一致。

反面教材：Read Coalescing 过早合入 Trunk 后证伪，见 [[DEC-061]]。
流程细则见 [[BEH-018]]…[[BEH-020]]；目录边界见 [[ARCH-008]]。
