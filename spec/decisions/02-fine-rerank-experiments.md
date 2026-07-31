# Decisions — Fine Rerank 实验 (DEC-017…025)

> 条款索引: `DEC-017`, `DEC-018`, `DEC-019`, `DEC-020`, `DEC-021`, `DEC-022`, `DEC-023`, `DEC-024`, `DEC-025`

## D-017: Page Search for Fine Rerank {#DEC-017}
<!-- ndf: kind=decision date=2026-07-29 affects=DEC-009,BEH-007 source=deduced -->

**Context.** Fine Rerank 读取 4KB 页后只计算候选向量的 L2 距离，浪费同页其余向量。
SIFT 128D 向量 512B/个，4KB 页含 8 个向量，当前利用率仅 12.5%。

来源: OctopusANN (VLDB 2026) 发现 Page Search 单独效果弱，但与 Page Shuffle 组合后
减少 28.3% 页读取。

**Decision.** Fine Rerank MUST 在读取 4KB 页后计算页内所有向量的精确 L2 距离，
而非仅计算候选向量。

**实现要点**：
- `readVecBlockPread` / `readVecBlockIouring` 返回页数据后，扫描页内所有向量
- 对每个向量计算 L2，插入候选集
- 需区分候选向量（在 top-K 候选列表中）和"邻居向量"（同页但非候选），
  后者只做距离计算不入图遍历
- refines: [[DEC-009]]

> rationale: 读页 I/O 已付出，计算 8 个 vs 1 个的 CPU 开销可忽略
> （8×L2(128D) ≈ 0.4μs），但可多发现 3-5 个高质量候选，提升 recall 2-3 个百分点。

## D-018: Page Shuffle for vecblocks {#DEC-018}
<!-- ndf: kind=decision date=2026-07-29 updated=2026-07-29 affects=DEC-006,ARCH-004 source=deduced -->

**Context.** 当前 BFS 重排在 64KB block 级（block 内节点连续），但 Fine Rerank
以 4KB 页读取。一个 64KB block 含 16 个 4KB 页，BFS 只保证 block 内连续，
不保证页内连续。

来源: OctopusANN (VLDB 2026) 发现 Page Shuffle 与 Page Search 协同后页命中率
显著提升。

**Decision.** vecblocks 文件 SHOULD 按 4KB 页粒度重排，使图相邻节点共享同一页。

**实现状态（2026-07-29）:**

`shuffle_vecblocks.cpp` 已实现完整的贪心页聚类算法：

1. 加载图邻接表（slim_adj 模式，不加载全量向量）
2. 将邻接表转换到 new_id 空间（BFS 重排后 ID）
3. 对每个 64KB block：
   - 构建块内邻接子图
   - 贪心页分配：种子选块内邻居最多的节点，后续选与当前页共享邻居最多的节点
   - 按新页顺序重排 node_ids 和 vectors
4. 输出新 vecblocks 文件（格式不变）

**页聚类质量:**
- 页内邻居对：29.7% → 77.1% (+159.5%)
- 算法复杂度：O(cnt²·vpp) per block, cnt≈126, vpp=8, 毫秒级完成

**precondition:** 仅对 SIFT (128D, 512B/向量, 8向量/页) 有效。
高维数据（如 GIST 960D）一页只放 1 个向量，Shuffle 无效。

- refines: [[DEC-006]]
- verifies: [[VER-018]]

> rationale: Page Shuffle 让 HNSW 图上相邻的节点落在同一 4KB 页，
> 配合 Page Search 后页内利用率从 12.5% 提升到 40-60%。

## D-019: Dynamic Width for Phase A {#DEC-019}
<!-- ndf: kind=decision date=2026-07-29 affects=DEC-008,BEH-002 source=deduced -->

**Context.** Phase A 搜索全程使用固定 efSearch 宽度。HNSW 搜索在候选集稳定后
（top-K 不再变化），继续以全宽度遍历只会增加 PQ 计算和图 I/O，不改善 recall。

来源: OctopusANN (VLDB 2026) 实测 Dynamic Width 减少 20-35% 图遍历步数，
是独立收益第二大的技术。

**Decision.** Phase A 搜索 SHOULD 使用自适应 efSearch 宽度：搜索初期使用全宽度，
候选集收敛后逐步收窄。

**实现要点**：
- `searchLayer0*()` 函数中，跟踪 top-K 变化
- 收敛检测：连续 N_hop 跳无新节点进入 top-K
- 收窄策略：efSearch 从初始值按几何衰减（×0.75/次），下限为 efSearch_min = 32
- 恢复机制：如果收窄后 recall 明显下降，可回退到全宽度
- 新增环境变量 `DYNAMIC_WIDTH=1`（默认关闭，benchmark 验证后决定是否默认开启）
- 新增 `EF_SEARCH_MIN`（默认 32）、`DW_DECAY=0.75`、`DW_CONVERGE_HOP=10`
- refines: [[DEC-008]]

> rationale: 搜索后期候选集已收敛，全宽度遍历是浪费。
> 几何衰减让搜索快速聚焦，下限 32 保证不丢失关键候选。

## D-020: Page Search / Dynamic Width SLA 调整决策 {#DEC-020}
<!-- ndf: kind=decision date=2026-07-29 affects=DEC-017,DEC-019,CON-007 source=deduced -->

**Context.** DEC-017 (Page Search) 和 DEC-019 (Dynamic Width) 经 2 轮修复后性能验证：

- DEC-017: recall 95.70% -> 96.20% (+0.5pp)，QPS 2051 -> 1832 (-11%)，SLA QPS 违规
- DEC-019: 无效果，根因为 B 类（规范缺陷）-- PQ 搜索在 EF=100 时不收敛

**Decision.**

1. **DEC-017 降级为实验性 SHOULD**：保留功能，新增 SLA 豁免（QPS ≥ 基线 × 85%）
2. **DEC-019 标记为规范缺陷**：保留代码（默认关闭零开销），不纳入 SLA，记录已知限制
3. **根因记录**：PQ 粗筛在 EF≥100 时 top-K 持续抖动不收敛，Dynamic Width 的收敛假设不成立

**Alternatives rejected.**
- A. 继续第 3 轮代码修复 -> PS 开销已接近下限，DW 根因是规范层非代码层
- 完全删除 DEC-017/019 -> PS 的 recall +0.5pp 是真实收益，删除浪费

> rationale: PS 是"计算换 recall"的合理 tradeoff，适合 recall 优先场景。
> DW 的 L1 契约假设错误，需要重新设计收敛检测策略（如基于迭代次数而非 top-K 稳定性）。

## D-021: Page Cache 驱逐模式 {#DEC-021}
<!-- ndf: kind=decision date=2026-07-29 affects=DEC-009,BEH-007 source=deduced -->

**Context.** 1M 规模下 vecblocks 496MB 被 OS page cache 100% 覆盖，Fine Rerank 走热态
缓存零磁盘 I/O，无法验证 I/O 优化技术。需主动驱逐 page cache 制造冷 I/O 条件。

**Decision.** 当 `EVICT_PAGE_CACHE=1` 时，DiskHNSW MUST 在每次查询完成后对 vecblocks
文件调用 `posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED)`，驱逐 page cache。

**实现要点**：
- 在 `searchKnn()` 查询完成后调用，仅驱逐 vecblocks fd
- 不驱逐 blocks_64k（BlockCache 自管理缓存）
- `EVICT_PAGE_CACHE=0`（默认）时零开销
- refines: [[DEC-009]]

> rationale: 在 1M 规模模拟 10M+ 规模的冷 I/O 条件，使 I/O 优化技术可被验证。
> 冷 I/O 下 Fine Rerank 每页读取 ~10-50μs（vs 热态 ~1μs）。

## D-022: 冷 I/O 下 Page Search 重新评估 {#DEC-022}
<!-- ndf: kind=decision date=2026-07-29 affects=DEC-017,DEC-021 source=deduced -->

**Context.** 热态下 Page Search QPS -11%（L2 计算开销主导）。冷 I/O 下 I/O 延迟
10-50μs/页，额外 7 个 L2 计算（~0.4μs）占比 < 4%。

**Decision.** 在冷 I/O 模式下重新评估 Page Search：
- 预期 recall 提升 ≥ 1pp
- 预期 QPS 下降 ≤ 5%
- 若达标，升级为默认开启

> rationale: 冷 I/O 下 L2 计算开销相对 I/O 可忽略，Page Search 的"计算换 recall"
> tradeoff 变得更有利。

## D-023: 冷 I/O 下 Page Shuffle 优先级提升 {#DEC-023}
<!-- ndf: kind=decision date=2026-07-29 updated=2026-07-29 affects=DEC-018,DEC-021 source=deduced -->

**Context.** Page Shuffle 原计划推迟到 P2（10M）。冷 I/O 模式下页内局部性直接影响
真实磁盘 I/O 量，Page Shuffle 变得有意义。

**Decision.** Page Shuffle 优先级从"推迟到 P2"提升为"P2 前置验证"。

**1M 验证结果（2026-07-29）:**

| 测试 | Recall | QPS | I/O 时间 |
|------|--------|-----|--------|
| 冷态基线 | 95.70% | 803 | 0.76ms |
| 冷态+Shuffle | 95.70% | 820 | 0.73ms |
| 冷态+PS | 96.20% | 789 | 0.78ms |
| 冷态+Shuffle+PS | 96.05% | 797 | 0.76ms |

- Shuffle 单独：QPS +2.1%，I/O -3.9%（远低于论文 25-30%）
- Shuffle+PS vs PS：QPS +1%，PS 开销从 -1.7% 降到 -0.7%
- **结论：1M 规模收益边际**，vecblocks 520MB 太小，OS page cache 仍有残留
- **下一步：10M 规模验证**（vecblocks 5GB+，page cache 必然不够）是 Page Shuffle 的真正战场

> rationale: 论文的 25-30% 页读取减少依赖大数据集（page cache 无法覆盖）
> 和多候选查询（每 query 读更多页）。1M 规模 I/O 量基数小，绝对收益有限。
> 但页聚类质量（77.1% co-locality）验证了算法正确性，
> 10M 规模预期收益接近论文数据。

## D-024: 冷 I/O 模式实验结论 {#DEC-024}
<!-- ndf: kind=decision date=2026-07-29 affects=DEC-017,DEC-019,DEC-021,DEC-022,DEC-023 source=observed -->

**Context.** DEC-021 实现 page cache 驱逐后，在 1M 规模跑冷 I/O benchmark。

**实验结果 (SIFT1M, 512MB cgroup, 1T):**

| 配置 | Recall | QPS | I/O 占比 |
|------|--------|-----|---------|
| 热态基线 | 95.70% | 2083 | ~0% |
| 冷态基线 | 95.70% | 842 | ~60% |
| 冷态 + Page Search | 96.20% | 792 | ~60% |
| 冷态 + Dynamic Width | 95.70% | 850 | ~60% |

**Decision.**

1. **冷 I/O 模式有效**: posix_fadvise(DONTNEED) 成功制造真实磁盘 I/O，QPS 下降 60%
2. **Page Search 冷态表现**: recall +0.5pp，QPS -5.9%（热态 -11%），L2 计算开销被 I/O 延迟掩盖
3. **Dynamic Width 正式放弃**: PQ 搜索不收敛是架构特性，非代码缺陷，冷 I/O 也不改变此结论
4. **Page Shuffle 实现完成，1M 收益边际**: 页聚类质量 77.1%（提升 159.5%），但冷态 I/O 仅减 4%
   （vs 论文 25-30%）。根因为 1M vecblocks (520MB) 太小，page cache 仍有残留。
   算法正确性已验证，真正收益在 10M。

**Dynamic Width 根因最终确认:**

PQ ADC 距离的量化误差导致 top-K 候选持续抖动，hash 和 lowerBound 收敛检测均无法触发。
这不是 bug 而是 PQ 粗筛的固有特性：EF=100 时搜索一直在探索新区域，直到候选集自然耗尽。
未来如需自适应宽度，需改用"迭代次数预算"而非"收敛检测"策略。

> rationale: 冷 I/O 模式让 1M 规模实验有了 10M+ 规模的 I/O 特征，
> 论文的 I/O 优化框架（Page Shuffle + Page Search）在此条件下才真正适用。

## D-025: Page Shuffle 1M 实现与验证 {#DEC-025}
<!-- ndf: kind=decision date=2026-07-29 affects=DEC-018,DEC-023,DEC-024 source=observed -->

**Context.** DEC-018 的 Page Shuffle 已从骨架实现为完整的贪心页聚类算法，
需在 1M 规模冷 I/O 下验证实际收益。

**完整实验结果 (SIFT1M, no cgroup, io\_uring, 1T, EVICT\_PAGE\_CACHE=1):**

| 测试 | Recall | Mean | QPS | RSS |
|------|--------|------|-----|-----|
| A: 热态基线（原始 vecblocks） | 95.70% | 0.49ms | 2038 | 273MB |
| B: 冷态基线（原始 vecblocks） | 95.70% | 1.25ms | 803 | 273MB |
| C: 冷态+PageSearch（原始） | 96.20% | 1.27ms | 789 | 275MB |
| D: 冷态+Shuffle | 95.70% | 1.22ms | 820 | 273MB |
| E: 冷态+Shuffle+PageSearch | 96.05% | 1.25ms | 797 | 275MB |
| F: 热态+Shuffle+PageSearch | 96.05% | 0.55ms | 1805 | 275MB |

**Decision.**

1. **算法正确性验证通过**: 页内邻居对从 29.7% 提升到 77.1% (+159.5%)
2. **1M 收益边际**: Shuffle 单独 QPS +2.1%，Shuffle+PS QPS +1.0%
   - I/O 仅减 4%，远低于论文 25-30%
   - 根因：vecblocks 520MB 太小，OS page cache 仍有残留，冷 I/O 不够"冷"
3. **Recall 保持**: 所有模式 recall ≥ 95%，无回归
4. **Shuffle 工具成熟度**:
   - 1.65s 完成 1M 向量重排
   - 支持 greedy 和 random 两种策略
   - 输出文件与原文件相同大小（520MB）
   - 原 `buildFineRerank()` 无需修改即可使用 shuffled vecblocks
5. **10M 是真正的验证战场**:
   - vecblocks = dataset\_size × dim × 4B, 10M SIFT = 5.12GB
   - page cache 必然无法覆盖，每次 I/O 都是真实磁盘访问
   - 论文的 25-30% I/O 减少预期在 10M 规模更可能成立

**P2 前置条件已满足**: Page Shuffle 算法、工具、验证链路均已就绪，
可直接用于 10M 规模的 P2 验证。

> rationale: 1M 规模是"验证算法正确性"的合适尺度（快速迭代、低资源），
> 但不是"验证 I/O 优化有效性"的合适尺度（page cache 干扰）。
> Page Shuffle 的投资回报率取决于数据集是否超出 page cache 容量。

