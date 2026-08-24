# Decisions — 规模与 I/O (DEC-026…033)

> 条款索引: `DEC-026`, `DEC-027`, `DEC-028`, `DEC-029`, `DEC-030`, `DEC-031`, `DEC-032`, `DEC-033`

## D-026: HELMSMAN 启示——图 vs 聚类的范式分歧与 P2 路线图确认 {#DEC-026}
<!-- ndf: kind=decision date=2026-07-29 source=deduced derived-from=REF-HELMSMAN -->

**Context.** HELMSMAN (OSDI 2026) 论文为小红书生产系统，用聚类 ANNS + 全闪存
替代内存 HNSW，节省 >90% 硬件成本。论文验证了图方法在大规模 SSD 场景的根
本性缺陷：图遍历产生串行 I/O 依赖链，无法利用 SSD 带宽。

但 HELMSMAN 的目标场景（100B 向量、分布式、90% recall）与 DiskHNSW（1M→100M、
单机、≥95% recall）存在本质差异。

**Decision.**

1. **确认 P2（10M）仍用图方法**：
   - 10M SIFT vecblocks ≈ 5GB（仍可能部分被 page cache 覆盖）
   - 图遍历的 I/O 串行化在 10M 规模尚未成为主导瓶颈
   - 我们的 95% recall 目标在聚类方法下难以达到（聚类天然有 recall 上限 ~90%）
   - Page Shuffle + Page Search 在 10M 冷 I/O 下预期有更大收益

2. **P3（100M）需重新评估范式**：
   - 100M vecblocks ≈ 50GB，page cache 完全失效
   - 图遍历每 query 约 100-200 次 4KB 串行 I/O = 1-2ms 延迟（可接受但接近极限）
   - 若 P2 验证图遍历在 10M 下 I/O 占比 >70%，P3 需考虑混合方案

3. **不关闭聚类路径**：
   - 将聚类 ANNS 作为 P3 的备选范式，与图方法形成 A/B 对比
   - HELMSMAN 的"SPANN 聚类 + SPDK"可作为参考架构
   - 论文的 learned pruning 思路可独立于聚类范式借鉴

4. **不立即引入 SPDK**：
   - SPDK 需要额外硬件绑定和运维复杂度
   - P2 阶段 io_uring 已足够（10M 规模 I/O 量有限）
   - P3 决策时根据 I/O 瓶颈程度重新评估

**Alternatives rejected.**
- 立即转向聚类方法 → 丢弃图方法已有的 recall 优势（95% vs 90%）
- 立即引入 SPDK → P2 规模不需要，过早引入增加复杂度
- 完全忽略 HELMSMAN → 论文的"图方法 I/O 瓶颈"预警是真实风险

> rationale: HELMSMAN 的成功验证了"聚类+SSD"的可行性，但聚类天然 recall 上限
> 与我们的 ≥95% 目标存在差距。图方法在 1M-10M 规模仍是正确选择，
> 但 100M+ 需要重新评估。这不是"图 vs 聚类"的二选一，
> 而是"什么规模切换到什么方法"的路线图问题。

## D-027: 用户态 I/O 在大规模时的必要性评估 {#DEC-027}
<!-- ndf: kind=decision date=2026-07-29 status=superseded-by=DEC-030 source=deduced derived-from=REF-HELMSMAN,DEC-009 -->

> **Status:** `superseded-by=DEC-030`（其后 DEC-030 再被 [[DEC-059]] supersede）。
> 本决策第 3 点“当前不引入 O_DIRECT”已被 [[DEC-030]]→[[DEC-059]]（O_DIRECT 性能地板）
> 与 [[DEC-039]] / [[DEC-057]]（诚实基准）取代。SPDK / P3 评估意图见 [[DEC-060]] Alternatives
> 与 DEC-030 历史 §4（当前阶段不引入 SPDK）。
> 下文保留为历史上下文，不再作为现行 I/O 真相源。

**Context.** HELMSMAN 论文验证了内核 I/O 栈（含 io_uring）仅利用 SSD 带宽的
26-59%，而 SPDK 用户态 I/O 可达 85%（Gen4）和 70%（Gen5）。

当前 DiskHNSW 使用 io_uring（Fine Rerank 4KB 页读）和 pread（多线程模式），
在 1M 规模下 I/O 不是瓶颈（热态 page cache 零 I/O，冷态 I/O 占比 ~60%）。

**Decision.**

1. **P2（10M）保持 io_uring**：
   - 10M 规模 I/O 量仍有限（每 query ~100-200 页），io_uring 带宽足够
   - io_uring 的提交/完成队列开销在单线程模式下可接受
   - SPDK 的运维成本（NVMe 绑定、大页内存）在 P2 阶段不划算

2. **P3（100M）纳入 SPDK 评估**：
   - 触发条件：I/O 占比 >80% 且 io_uring 带宽利用率 >80%
   - 替代方案：多 SSD 条带化 + io_uring 多队列（先尝试，成本更低）
   - SPDK 作为最终兜底

3. **当前不引入 O_DIRECT 优化**：
   - FINE_BUFFERED=1 已验证 page cache 热区零 I/O
   - O_DIRECT 仅在有确定性 I/O 模式时有益（如固定大小的 cluster 读）
   - 图遍历的 I/O 模式不规则，O_DIRECT 可能降低性能

> rationale: io_uring 是"够用"方案，SPDK 是"极致"方案。
> 过早优化是万恶之源——Helmsman 需要 SPDK 是因为它 24/7 跑 10B+ 向量，
> 我们在 1M-10M 阶段不需要。但 P3 设计预留 io_uring → SPDK 的切换接口。

## D-028: 学习式剪枝——Fine Rerank 的自适应优化方向 {#DEC-028}
<!-- ndf: kind=decision date=2026-07-29 source=deduced derived-from=REF-HELMSMAN,DEC-017,DEC-020 -->

**Context.** HELMSMAN 的 LLSP（Leveling-Learned Search Pruning）用 GBDT 模型预测
最优 nprobe 层级，替代固定剪枝参数。效果：1.1-1.6× 吞吐提升，>80% query 达到
目标 recall（固定剪枝仅 40%）。

当前 DiskHNSW 的 Fine Rerank 使用固定参数（REFINE_EF、PAGE_SEARCH on/off），
所有 query 用相同策略。但不同 query 的难度不同：
- 容易的 query：EF=50 即可收敛，REFINE_EF=100 浪费 I/O
- 困难的 query：需要更多候选 + Page Search 才能维持 recall

**Decision.**

1. **探索适配 DiskHNSW 的学习式剪枝（P2.5，低优先级）**：
   - 输入特征：query 向量、PQ 距离分布（粗筛阶段的前 N 个候选距离）、top-k
   - 预测目标：决定是否开启 Page Search、REFINE_EF 值
   - 输出：per-query 的 (enable_ps, refine_ef) 决策
   - 模型：轻量 GBDT（LightGBM）或小型 MLP，推理 <1μs

2. **先做 profiling 再决定**：
   - 在 10M 规模收集 per-query 的 I/O 量、recall、延迟
   - 分析 query 难度分布（多少 query 需要/不需要 Page Search）
   - 如果 Page Search 的 recall 增益集中在少数困难 query，剪枝收益大
   - 如果所有 query 均匀受益于 Page Search，剪枝无意义

3. **不作为 P2 的 blocking 项**：
   - P2 优先验证基础 I/O 优化（Page Shuffle + Page Search 冷态效果）
   - 学习式剪枝是 P2 之后的优化方向，不是 P2 的前置条件

**Alternatives rejected.**
- 立即实现 LLSP → 缺乏 10M 规模的 profiling 数据，暗箱设计风险大
- 照搬 HELMSMAN 的 nprobe 层级设计 → 我们的 nprobe 概念不同（图搜索的 ef 而非聚类 probe 数）

> rationale: HELMSMAN 的成功经验表明"自适应比固定好"，
> 但我们的搜索架构不同（图 vs 聚类），不能直接照搬。
> 先收集 10M 规模的 query 难度分布数据，再设计适配的学习式剪枝方案。

## D-029: DEEP10M 瓶颈转移——P2 路线图重新校准 {#DEC-029}
<!-- ndf: kind=decision date=2026-07-29 affects=DEC-018,DEC-022,DEC-023,DEC-026,P2 source=observed -->

**Context.** DEEP10M (96D, 9.99M) 冷 I/O 6 组 benchmark 完成。
预期：Page Shuffle + Page Search 在冷 I/O 下减少 25-30% I/O。
实际：I/O 占比仅 7%（vs SIFT1M 的 60%），两者均无效。

**实测瓶颈分析:**

```
SIFT1M (1M):  PQ[10%] + 图[30%] + I/O[60%]  → Page Shuffle 有效
DEEP10M (10M): PQ[80%] + 图[13%] + I/O[7%]   → Page Shuffle 无效
```

| 指标 | SIFT1M | DEEP10M | 说明 |
|------|--------|---------|------|
| 热态 QPS | 2038 | 74.9 | PQ 计算主导 |
| 冷态 QPS | 803 | 69.8 | I/O 仅增 1ms |
| I/O 占比 | 60% | 7% | 瓶颈转移 |
| Page Shuffle gain | +2.1% | ~0% | 优化了错误瓶颈 |
| Page Search recall | +0.5pp | +0.05pp | 10 向量/页已饱和 |

**Decision.**

1. **P2 I/O 优化策略降级**:
   - Page Shuffle (DEC-018) 在 I/O 非瓶颈规模下不产生收益，保留算法但标记为 P3 技术
   - Page Search (DEC-017) 在 ≥10 向量/页的维度下无增益，功能保留但关闭默认推荐

2. **P2 真正瓶颈识别**:
   - **PQ 计算**: M=32×256 centroids 的 ADC 距离占 ~80% query 时间
   - **内存压力**: CSR 邻接表 1.2GB，无法在 1GB cgroup 运行
   - **图遍历**: ~13% query 时间，仍有优化空间

3. **P2 目标重新校准**（**P2 过渡验收**，不覆盖 Charter ≥95% SoT）:
   - Recall ≥94% 作为 P2 阶段过渡验收下限（接受 M=32 PQ 固有精度上限）；
     生产 / Charter / CON 仍以 ≥**95%** 为 SoT（见 [[CHR-006]]、[[CHR-007]]）
   - QPS 目标从 >500 调整为按比例缩放（4T 预期 ~300 QPS）
   - 内存目标从 1GB cgroup 放宽到 3GB+

4. **P2 新优化方向**:
   - **PQ SIMD 加速**: AVX2/VNNI 批量 ADC 距离计算
   - **PQ 量化压缩**: M=24 (dsub=4) 在 92% recall 下的性能 tradeoff
   - **图遍历优化**: 更激进的软件预取 + 搜索剪枝

> rationale: DEEP10M 揭示了与 SIFT1M 本质不同的瓶颈模式。
> I/O 优化技术（Page Shuffle/Search）的物理价值需要 I/O 占比 >30%
> 才能体现——这可能在 100M+ 规模才满足。
> 10M 规模是"优化 PQ 计算"和"控制内存压力"的战场。

## D-030: Page Cache + Disk 两层 I/O 架构 + O_DIRECT 诊断模式 {#DEC-030}
<!-- ndf: kind=decision date=2026-07-29 updated=2026-07-31 affects=DEC-009,ARCH-003 source=deduced -->
<!-- ndf: superseded-by=DEC-059 -->

> **Status:** `superseded-by=DEC-059`（2026-07-31 战略重新校准）。
> 本决策第 1 点"page cache 是免费的"已修正为"page cache 与匿名内存共享 cgroup 预算"。
> 本决策第 2 点"FINE_DIRECT 降级为诊断/测试模式"已修正为"FINE_DIRECT 是优化基座和性能地板"。
> O_DIRECT 的定位由 [[DEC-059]] 接管，I/O 优化方案见 [[DEC-060]]。
> 下文保留为历史上下文，不再作为 I/O 真相源。

**Context.** 当前 FINE_RERANK 在 `FINE_BUFFERED=1` 模式下依赖 OS page cache 提供
4KB 页的快速访问，OS 自动管理冷热分层--page cache 提供缓存层。

如果需要模拟"无 page cache"场景（内存受限 benchmark、大规模 cold start 测试），
O_DIRECT + io_uring 可以绕过 page cache 做真实磁盘 I/O 对照。

**Decision.**

1. ~~**确认默认架构：BlockCache(内存) -> Page Cache(OS免费) -> NVMe(磁盘)**~~
   - 修正（[[DEC-059]]）：Page cache 与匿名内存共享 cgroup 预算，不是"免费"的。
   - FINE_BUFFERED=1 仍是推荐生产模式，但 page cache 可用量受限于 cgroup_limit - RSS。
   - 有内存时零 I/O，内存不够时自动驱逐 -> 适配"动态内存"场景

2. ~~**FINE_DIRECT=1 降级为诊断/测试模式**~~
   - 修正（[[DEC-059]]）：FINE_DIRECT 是优化基座和性能地板，非诊断工具。
   - 保留用于：冷 I/O 基准测试、cgroup 内存受限 benchmark、大规模性能地板
   - 实现：`open(O_RDONLY | O_DIRECT)` + io_uring 批量提交
   - O_DIRECT 路径优化见 [[DEC-060]]

3. **实测验证**：
   | 模式 | QPS | 说明 |
   |------|-----|------|
   | FINE_BUFFERED（默认） | 2,041 | page cache 热态零 I/O |
   | FINE_DIRECT=1（诊断） | 787 | 真实 NVMe I/O, 0.78ms/query |
   - FINE_DIRECT 验证了 O_DIRECT 路径正确性 ✅
   - recall 不变（95.70%）✅

4. **SPDK 路线**：P3 规模（100M+）如有多余 NVMe 设备，可迁移到 SPDK
   替代内核 I/O 层（非替代 page cache）。

- refines: [[DEC-009]]
- verifies: [[VER-030]]

> rationale: ~~Page cache 是免费的--OS 已经做好了冷热分层。~~
> 修正（[[DEC-059]]）：Page cache 与匿名内存共享 cgroup 预算，可用量 = limit - RSS。
> Buffered 模式仍是生产推荐，但 O_DIRECT 才是性能基座和优化目标。

## D-031: 页面级驱逐——消除 Page Cache 颠簸引起的 QPS 悬崖 {#DEC-031}
<!-- ndf: kind=decision date=2026-07-30 affects=DEC-030 source=observed -->

**Context.** Cgroup 内存限制扫描发现：page cache 可用空间低于工作集时，
QPS 出现 10× 断崖（1,973 → 196），OS 在页面驱逐和 LRU 管理上消耗大量 CPU。
这比直接用 O_DIRECT 还差（787 vs 196 QPS）。

用户期望：page cache 不足时应优雅退化，而非断崖。

**Decision.**

1. **在 Fine Rerank 完成后，批量驱逐本次查询刚读过的页面**：
   - 收集 fine rerank 读取的所有 page 号（已在上层收集，现成可用）
   - 排序去重 → 合并相邻页为 range
   - 对每个 range 调用 `posix_fadvise(fd, start, len, POSIX_FADV_DONTNEED)`
   - 效果：只驱逐 read-once 数据，保留跨 query 复用的热页

2. **启用方式**：`FINE_FADVISE=1` 环境变量（默认关闭，需与 FINE_BUFFERED 配合）
   - 与 FINE_DIRECT 互斥（一个有 page cache，一个没有）
   - 推荐搭配：`FINE_BUFFERED=1 FINE_FADVISE=1`（有 page cache，用完即弃）

3. **预期效果**：
   - 256MB cgroup：几乎无影响（page cache 充足，驱逐是 no-op）
   - 180MB cgroup：QPS 196 → 500+（消除颠簸，变成干净磁盘 I/O）
   - 成本：每 query 1-3 次 posix_fadvise 系统调用（<10μs）

4. **与 FINE_DIRECT 对比**：
   | 模式 | 如何读 | 如何释放 | 适用场景 |
   |------|--------|---------|---------|
   | FINE_BUFFERED | pread → page cache | OS 自动 LRU | 内存充足 |
   | FINE_DIRECT | O_DIRECT io_uring | 不占用 cache | 极端受限 |
   | FINE_BUFFERED+FINE_FADVISE | pread → page cache | 主动 page 级驱逐 | 内存紧张(新) |

- verifies: [[VER-031]]

> rationale: 不放弃 page cache 的好处（批量预取、跨 query 复用），
> 同时避免 page cache 颠簸的代价（LRU 维护 + 无效驱逐）。
> 类似于 CPU cache 的"non-temporal"访存指令——读一次就过，别占 cache line。

## D-032: 10× QPS 悬崖根因——Cgroup Memory Reclaim 非 I/O 瓶颈 {#DEC-032}
<!-- ndf: kind=decision date=2026-07-30 affects=DEC-031,CON-007 source=observed -->

**Context.** 尝试 FINE_FADVISE/FINE_DIRECT/降缓存来消除 180MB cgroup 的 10x QPS 悬崖，均失败。

| 方案 | 180MB QPS | 效果 |
|------|-----------|------|
| FINE_BUFFERED (基线) | 196 | — |
| + FINE_FADVISE | 163 | ❌ |
| FINE_DIRECT | 188 | ❌ |

**根因:** cgroup memory.max 被触发 59,773+ 次 → OS memory reclaim 消耗大量 CPU。
这不是 I/O 瓶颈，是 reclaim 瓶颈。

**Decision.**
1. 10x 悬崖是 cgroup 硬限制的必然结果
2. 缓解: 用 memory.high (软限制) 而非 memory.max (硬限制)；给 page cache 留 RSS + 2x 工作集
3. 代码层面: 压缩 CSR 图、上层 PQ 编码 → reduce process RSS
4. 任何 I/O 优化在 reclaim 风暴面前无效

> rationale: 这不是 I/O 问题，是 memory provisioning 问题。

## D-033: CSR 图裁剪 (Degree Cap) — 压缩进程基址内存 {#DEC-033}
<!-- ndf: kind=decision date=2026-07-30 affects=DEC-032,ARCH-004,CON-007 source=deduced -->

**Context.** 进程 RSS 101MB 中 CSR 邻接表占 47MB。降低 RSS 是消除 cgroup reclaim
悬崖的最直接手段——每减少 1MB 进程内存，page cache 多 1MB 空间。

**Decision.** 对 HNSW 图实施 Degree Cap 裁剪：
- L0 每节点最多保留 K 条边（K = 16/20/24）
- 保留 angle-wise 最分散的邻居（MRNG 启发式）
- 预期：CSR 47MB → 25-35MB（K=16 → 47%，K=20 → 56%）

**实现**：已有 `prune_graph.cpp` 工具，含 Degree Cap + MRNG 两种策略
- 输入：graph + bfs → 输出：裁剪后的 graph
- 需重新生成 vecblocks + route table + PQ codes

**验证**：180MB cgroup 下 QPS 需 ≥ 800

- verifies: [[VER-033]]

> rationale: 图裁剪是投入产出比最高的内存压缩手段——
> 1 行代码不改（工具已有），直接见效。

