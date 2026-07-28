# Charter — 系统目标与范围

## 系统目标 {#OBS-CHR-001}
<!-- ndf: kind=arch level=L0 layer=L0 status=stable since=0.1 source=observed -->

DiskHNSW MUST 在 cgroup 内存限额（≥512MB）下，使用磁盘驻留向量数据，实现与全内存 HNSW 可比的向量搜索召回率（≥95%），同时将常驻内存控制在限额内。

**核心业务实体（从代码强行归纳）：**

1. **HNSW 图结构** (`GraphStructure` — `common.h:113-136`): 分层图，包含节点层级、向量、标签、邻接表，搜索时通过贪心下降 + best-first 遍历
2. **BlockCache** (`BlockCache` — `block_cache.h:116-430`): LRU 缓存的磁盘块管理器，按需加载 64KB/256KB 块，可插拔布局和替换策略
3. **PQ 编码** (`PQParams` + `pq_codes_` — `disk_hnsw.h:37-43`): Product Quantization 将 128 维向量压缩为 32 字节，用于 Phase A 零 I/O 粗筛
4. **两层搜索**: Phase A (PQ ADC 粗筛) + Phase B (精确 L2 精排)，精排通过 4KB 页粒度 I/O 读取候选向量
5. **数据 Pipeline**: build_index → extract_graph → bfs_reorder → write_blocks → write_blocks_veconly → train_pq → gen_gt
6. **io_uring 异步 I/O** (`IoUring` — `io_uring_wrapper.h:57-363`): 内核异步 I/O，批量提交，O_DIRECT 对齐

## Scope {#OBS-CHR-002}
<!-- ndf: kind=arch level=L0 layer=L0 status=stable since=0.1 source=observed -->

- **IN**: 向量搜索（L2 距离）、PQ 训练与编码、BFS 重排优化块局部性、CSR 邻接表压缩、图引导预取、多线程并发搜索
- **IN**: cgroup 内存受限部署、数据 pipeline 工具链（build_index/extract_graph/bfs_reorder/write_blocks/write_blocks_veconly/gen_route/verify）
- **IN**: 可插拔缓存架构（LayoutProvider 接口 + ReplacementPolicy 接口）
- **OUT**: 增量插入/删除（当前只读搜索，无 insert/delete API）
- **OUT**: 多租户 QoS、分布式部署、持久内存支持
- **OUT**: GPU 加速（规划在 P5 阶段）

## Non-Goals {#OBS-CHR-003}
<!-- ndf: kind=info layer=L0 status=stable since=0.1 source=observed -->

- **不是**通用向量数据库：无 CRUD、无持久化日志、无 WAL
- **不是**实时插入系统：索引构建是离线 batch 操作
- **不是**跨平台方案：依赖 Linux 5.1+ (io_uring)、x86 AVX2、C++17

---

<!-- ════════════════════════════════════════════════════════════════ -->
<!-- INTENT- 条款：基于 README、代码结构和性能数据的推断性规范   -->
<!-- source=deduced 表示条款源自全局理解，非从单一代码实体提取 -->
<!-- ════════════════════════════════════════════════════════════════ -->

## 业务价值主张 {#INTENT-CHR-001}
<!-- ndf: kind=arch level=must layer=L0 status=stable since=0.2 source=deduced -->

DiskHNSW 解决的核心商业问题：**在内存受限的计算环境中实现高召回率向量近似搜索**。

具体价值场景：

1. **容器化部署**：Kubernetes Pod 通常有 512MB-2GB 内存限制，hnswlib 需 726MB（1M SIFT）
   无法部署。DiskHNSW 在 512MB 下实现 95.70% recall / 2780 QPS（单线程），使向量搜索
   可以作为 sidecar 或微服务运行在标准容器规格中
2. **边缘计算**：ARM/x86 边缘节点内存有限（2-4GB），需同时运行应用逻辑和 AI 推理。
   DiskHNSW 的内存占用仅为全内存方案的 37%（269MB vs 726MB），剩余内存可供模型推理
3. **成本优化**：云服务器内存是主要成本因子。1M 向量场景下 hnswlib 需 ≥1GB 实例，
   DiskHNSW 可在 512MB 实例上运行，**实例成本降低约 50%**
4. **规模化可行性**：10M/100M 向量场景下全内存方案分别需 7GB/70GB，不可行。
   DiskHNSW 的磁盘卸载架构使 10M 向量在 1GB 内存下可运行，100M 在 2-4GB 下可运行

> rationale: 内存是向量搜索的商业瓶颈而非算力。CPU 单次搜索仅 0.5ms，
> 但 1M 向量需 488MB 内存——这是硬成本，不可压缩。DiskHNSW 通过 PQ 压缩
> + 磁盘卸载把内存从 488MB 降到 30MB（PQ codes），用 I/O 换内存。

## 目标用户画像 {#INTENT-CHR-002}
<!-- ndf: kind=arch level=should layer=L0 status=stable since=0.2 source=deduced -->

DiskHNSW 的目标用户：

1. **搜索推荐系统工程师**：需要在内存受限环境中部署 ANN 搜索服务，处理百万级商品/内容向量
2. **边缘 AI 开发者**：在 Jetson / 树莓派等设备上部署向量搜索，内存预算 1-2GB
3. **云原生团队**：希望将向量搜索作为微服务部署，受限于 K8s Pod 内存配额
4. **学术研究者**：研究内存-磁盘混合索引结构、PQ 近似搜索、I/O 优化

Non-target 用户：需要毫秒级实时插入的在线向量数据库用户（如 Milvus / Pinecone 用户）。

## 关键性能承诺 {#INTENT-CHR-003}
<!-- ndf: kind=constraint level=must layer=L0 status=stable since=0.2 source=deduced -->

DiskHNSW 对 SIFT1M（128 维，100 万向量）MUST 达成以下指标：

| 指标 | 值 | 条件 | 验证方式 |
|------|-----|------|----------|
| Recall@10 | ≥ 95% | 512MB cgroup | benchmark vs GT |
| QPS (单线程) | ≥ 2000 | 512MB cgroup, CSR 压缩后 | benchmark |
| QPS (4 线程) | ≥ 5000 | 512MB cgroup | benchmark |
| RSS | ≤ 300MB | 512MB cgroup | /proc/self/status |
| 内存节省 | ≥ 2.5x | vs hnswlib 726MB | 对比测试 |

> rationale: 95% recall 是生产可接受的最低召回率阈值；
> 2000 QPS 是单线程交互式搜索的可用阈值（<0.5ms 延迟）。

## 演进路线意图 {#INTENT-CHR-004}
<!-- ndf: kind=arch level=should layer=L0 status=stable since=0.2 source=deduced -->

DiskHNSW 的设计意图是**从 1M 验证走向 100M 生产**：

- **P0-P1（已完成）**：1M 规模下验证内存卸载 + 压缩 + 图裁剪的可行性与边界
- **P2（下一步）**：10M 规模验证——这是“内存受限磁盘搜索”叙事的关键战场。
  vecblocks 5GB 超出任何合理 page cache，冷 I/O 成为主导因素。
  hnswlib 需 7GB 会 OOM，DiskHNSW 目标在 1GB cgroup 下 recall≥95% / QPS>500
- **P3**：100M 规模——CSR varint 4.7GB 也需上磁盘，引入 CSR 分页 + 1-hop 预取
- **P4-P5**：分级存储、硬件亲和（NUMA/SPDK/GPU/PMEM）

每个阶段的核心验证：**“给定内存预算 M，DiskHNSW 能跑多大规模的向量搜索？”**

> rationale: 1M 规模下宿主机 page cache 能装下全部 496MB 向量数据，
> 掩盖了磁盘 I/O 优化的真实价值。只有在 vecblocks 超出 page cache 的规模下，
> 两阶段搜索 + 4KB 页精排 + io_uring 预取的架构优势才会显现。

## 设计约束（推断） {#INTENT-CHR-005}
<!-- ndf: kind=constraint level=should layer=L0 status=stable since=0.2 source=deduced -->

除 [[OBS-CHR-004]] 的硬约束外，以下软约束指导设计决策：

1. **零外部运行时依赖**：除 glibc 和 Linux 内核外，不依赖任何动态库（hnswlib 是 header-only，
   faiss 仅用于离线 Python 脚本）。SHOULD 保持单二进制部署能力
2. **Linux 优先**：不追求跨平台，利用 io_uring、O_DIRECT、cgroup v2 等 Linux 特有能力
3. **C++17 而非 C++20**：保持与主流编译器的兼容性，避免 C++20 coroutine/modules 的编译器差异
4. **离线索引构建**：搜索是在线路径，索引构建是离线 batch。不追求在线插入性能
5. **可测量性**：每个优化 MUST 有 benchmark 数据支撑，不做无数据的“感觉更快”

## 设计约束 {#OBS-CHR-004}
<!-- ndf: kind=constraint level=must layer=L0 status=stable since=0.1 source=observed -->

1. 常驻内存 MUST ≤ cgroup MemoryMax（典型 512MB）
2. 搜索召回率 MUST ≥ 95% (Recall@10 on SIFT1M)
3. 所有数据准备步骤 MUST 用同一套 base 数据（graph/PQ/GT 共享 node id 空间）
4. vecblocks 与 route table MUST 配套生成，不可跨版本混用
