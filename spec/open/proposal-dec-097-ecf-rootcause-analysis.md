# Proposal: DEC-097 - multi-thread-scaling 方向 E/C/F 收益受限根因分析

> track: poc
> 日期: 2026-08-11
> Status: proposal
> 场景: 负结果闭环 / DEC 归档
> 关联: [[DEC-074]] (A2+C2 promote), [[DEC-073]] (FVC promote), [[DEC-072]] (PQ 边界), [[DEC-070]] (WILLNEED), [[BEH-020]] (负结果闭环), [[BEH-027]] (WILLNEED_BG)

## 1. 背景

multi-thread-scaling POC (2026-08-05) 识别 6 个优化方向 (A-F)，目标消除 12T+ 瓶颈：
- WILLNEED 内核锁竞争 6.27% (osq_lock + queued_spin_lock)
- VisitedList memset 10.29% (1MB memset per search, cache bouncing)

**方向 A (WILLNEED 后台线程化)** 大获成功：A2 无锁 SPSC 方案 16T +72.8%，已 promote (DEC-074)。
**方向 B (WILLNEED 自适应禁用)** 已证伪 (16T+ -38%)，记录于 DEC-074。

本提案对 **方向 C (VisitedList 池化)、方向 E (DEEP10M I/O 优化)、方向 F (flat_vec_cache 调优)** 的收益受限进行根因分析，归档为 DEC-097。

## 2. 方向 C: VisitedList 线程局部池 — 收益边际化

### 2.1 实验结果

| 子方向 | 方案 | 4T QPS | 12T QPS | 16T QPS | 结论 |
|--------|------|--------|---------|---------|------|
| C1 | always-on thread_local pool | -15.6% | -8.2% | -5.1% | ❌ 负收益 |
| C2 | adaptive (T≥14 启用) | 0% (未触发) | 0% (未触发) | +6.0% | ✅ 边际正向 |

### 2.2 根因分析

**根因 1: thread_local 开销 > memset 节省 (C1 负收益)**

- 每个 VisitedList = 1MB (SIFT1M, uint8_t × 1M nodes)
- thread_local 初始化: 首次访问触发 zero-fill + TLS setup, ~50μs/thread
- memset 清零: 1MB memset ≈ 80μs (AVX2, L1 resident)
- C1 在 4T 下每个 query 需重置 VisitedList, thread_local 复用需 "clear" (部分 memset)
- 但 clear 仍需 memset 已用区域 + thread_local 的 TLS lookup 开销
- **净效果**: TLS overhead + partial memset > full memset (因为 full memset 已被 CPU prefetcher 优化)

**根因 2: cache bouncing 非 12T 瓶颈的根源**

- perf 显示 12T memset 10.29%，但这是 **所有线程合计**
- 单线程 memset 占比 ≈ 10.29% / 12 = **0.86%**，远非瓶颈
- 真正的 cache bouncing 来自 **VisitedList 的写访问** (mark visited)，而非 memset 初始化
- 池化解决的是 "重新分配" 问题，但 VisitedList 的分配本身就是 thread-local 的 (栈上或 per-thread arena)
- **结论**: 优化了一个不是瓶颈的环节

**根因 3: C2 阈值触发说明问题规模依赖**

- C2 仅在 T≥14 时有效 (+6%)，说明只有极高并发下 cache line 争用才可测量
- 16T 机器上 14T 是窄窗口，实际生产环境很少稳定运行在此区间
- 即使在 16T，+6% 也被 A2 的 +72.8% 完全稀释 (A2+C2 叠加后 C2 贡献 <3%)
- **本质**: VisitedList memset 是 O(N) 操作 (N=数据集大小)，HNSW 搜索是 O(log N)
- 随数据集增大，memset 占比下降，C 方向的天花板进一步降低

### 2.3 教训

- **perf 热点 ≠ 优化目标**: 合计 10.29% 看起来显著，但分摊到 12 线程后单线程仅 0.86%
- **thread_local 不是免费的**: TLS lookup + lazy init 开销在低中并发下可能超过其节省
- **自适应阈值是正确思路但收益有限**: C2 的设计正确 (高并发才启用)，但问题的绝对值太小

---

## 3. 方向 E: DEEP10M I/O 优化 (P3 CSR 上磁盘) — 未执行

### 3.1 方案描述

将 CSR (Compressed Sparse Row) 边表从 mmap 区域移到独立磁盘文件，
减少 FineRerank 阶段的 pread 数据量 (当前每 query 读 ~50 页，其中 ~40% 是边表数据)。

### 3.2 根因分析 (为何未执行)

**根因 1: 架构级改动的连锁影响过大**

- CSR 上磁盘影响: mmap 区域布局重设计 + block 结构变更 + FineRerank I/O 路径重写
- 连锁影响: block_cache 预取逻辑 + WILLNEED_BG 路径 + BFS reorder 管线
- 估算工作量: 2-3 周 (vs 方向 A 的 2 天)
- **ROI 不足**: SIFT1M 已达 Pareto 前沿 (30K QPS @512MB 16T)，主战场无需此优化

**根因 2: DEEP10M 瓶颈是 I/O 量而非 I/O 路径**

- DEC-070 验证: WILLNEED 对 DEEP10M 中性 (-0.4%)，因为:
  - 每 query majfault ≈ 68K 次 (SIFT1M 仅 5K)
  - 瓶颈是 **总 I/O 量** (3.7GB vecblocks >> page cache)，不是 I/O 时序
- CSR 上磁盘能减少单次 pread 的数据量，但 **不减少总 I/O 次数**
- 甚至可能恶化: CSR 独立文件 → 随机读取代替 block 内顺序读取 → 磁盘 seek 开销

**根因 3: DEEP10M PQ 已到天花板**

- DEC-072 确认: M=32+EF=300 是 Recall≥95% 唯一达标组合
- M=24 → Recall 94.05% (不达标)，OPQ 旋转 → Recall 1.25% (灾难)
- 即使 I/O 优化提升 QPS，Recall 约束锁死了参数空间，无法通过调参换取更多 QPS
- **本质**: DEEP10M 的问题是 **精度-速度 Pareto 前沿** 限制，不是 I/O 架构问题

**根因 4: 规模经济不对**

- DEEP10M (10M vectors, 96 dim) 是验证场景，非产品目标
- 真正的产品规模是 100M-1B，在那个规模下 I/O 架构需要根本性重新设计 (非 CSR 上磁盘能解决)
- 在 10M 规模投入架构级改动，既不能 validate 产品价值，也不能 reuse 到 100M 规模

### 3.3 教训

- **复杂度门槛**: 当改动复杂度 > 架构级时，必须有产品需求驱动，不能仅靠技术兴趣
- **I/O 量 vs I/O 路径**: WILLNEED 优化的是 I/O 时序 (串行→并行)，CSR 上磁盘优化的是 I/O 量 (减少单次读取)，但总 I/O 次数不变
- **Recall 约束锁定参数空间**: PQ 质量到天花板后，I/O 优化的收益无法转化为 QPS 提升 (被 EF=300 锁死)

---

## 4. 方向 F: flat_vec_cache 调优 — 范围受限

### 4.1 实验结果

| 配置 | FVC=4MB (旧默认) | FVC=64MB (新默认) | FVC=160MB (512MB 最优) | 结论 |
|------|------------------|-------------------|------------------------|------|
| SIFT1M 512MB 4T | 9,252 | - | 11,421 (+23.4%) | ✅ 已 promote (DEC-073) |
| SIFT1M 256MB 4T | - | 8,838 (最优) | - | ✅ 已 promote |
| DEEP10M 2GB 12T | - | 无效果 | 无效果 | ❌ 零收益 |
| SIFT1M 12T+ (多线程) | 边际 | 边际 | 边际 | ❌ 被 WILLNEED_BG 稀释 |

### 4.2 根因分析 (收益受限的维度)

**根因 1: 规模依赖性 — FVC 覆盖率随数据集增大急剧下降**

- SIFT1M: vecblocks 496MB, FVC=64MB → 覆盖 ~13% 节点 → 命中率 45-49%
- DEEP10M: vecblocks 3.7GB, FVC=64MB → 覆盖 ~1.7% 节点 → 命中率 <5%
- FVC 的效果完全依赖 "热向量集中度" (少数向量被频繁访问)
- SIFT1M 的热度分布允许 13% 覆盖率下 45% 命中率 (3.5x 放大)
- DEEP10M 的热度分散 (96 dim, 更均匀的访问)，放大效应消失

**根因 2: slot 架构天花板 — 命中率硬上限 45-49%**

- l4-cache-mgmt R2 D1 诊断: FVC 命中率 ceiling = 45-49%
- 原因: slot 架构 (per-query slot) 导致 LRU 粒度粗，部分热向量被 evict
- 即使增大 FVC 到 160MB，命中率仅从 45% → 49% (边际递减)
- **结论**: FVC 的架构设计本身限制了收益上限，不是参数调优能突破的

**根因 3: 多线程下被 WILLNEED_BG 稀释**

- FVC 的核心价值: 减少 FineRerank pread 次数 (热向量从 page cache 移到进程内)
- 但 WILLNEED_BG 已将 pread 路径并行化 (BG 线程提前 fadvise, pread 命中 page cache)
- 1T: FVC 是唯一 I/O 优化手段 → 效果显著 (+23.4%)
- 16T: WILLNEED_BG 消除了 pread 等待 → FVC 的边际收益被稀释到 <3%
- **本质**: FVC 和 WILLNEED_BG 优化同一瓶颈 (pread 延迟)，但 WILLNEED_BG 更彻底

**根因 4: DEEP10M 的 I/O 量瓶颈不受 FVC 影响**

- DEC-070: DEEP10M 每 query 68K majfault，FVC 64MB 只能消除 <5% 的 pread
- 即使 FVC 增大到 512MB (cgroup 不允许)，也只能覆盖 ~14% 节点
- DEEP10M 的瓶颈是 **总 I/O 量** >> cgroup page cache，不是热向量命中率

### 4.3 教训

- **缓存优化的有效前提**: 热度分布有显著倾斜 (Zipf-like)，均匀分布下缓存无效
- **架构天花板**: slot 架构的 LRU 粒度限制了命中率上限，参数调优无法突破
- **优化手段竞争**: 当多个优化手段作用于同一瓶颈时，后生效的收益会被稀释
- **规模敏感性**: SIFT1M 的成功不能外推到 DEEP10M，覆盖率是决定性因素

---

## 5. 跨方向综合分析

### 5.1 三个方向的共同模式

| 维度 | C (VisitedList) | E (CSR 上磁盘) | F (FVC 调优) |
|------|----------------|---------------|-------------|
| **误判瓶颈** | cache bouncing 非 12T 主要瓶颈 | I/O 路径非 DEEP10M 瓶颈 | FVC 命中率受 slot 架构限制 |
| **规模依赖** | 大数据集下 memset 占比下降 | 10M 规模不足以 justify 架构级改动 | 大数据集下覆盖率急剧下降 |
| **竞争优化** | A2 (WILLNEED_BG) 消除了 I/O 等待，C 的 memset 优化更不重要 | WILLNEED 对 DEEP10M 无效，说明 I/O 时序非瓶颈 | WILLNEED_BG 稀释 FVC 在多线程下的收益 |
| **天花板限制** | O(N) memset vs O(log N) 搜索 | Recall 95% 约束锁死参数空间 | slot 架构 45-49% 命中率上限 |

### 5.2 核心洞察

**A 方向成功而 E/C/F 受限的根本原因**:

A (WILLNEED_BG) 优化的是 **I/O 时序** (串行→并行)，这是一个 **架构级** 优化，
消除了 6.27% 的内核锁竞争 + 将 pread 从同步等待变为异步预取。

E/C/F 都试图优化 **次级瓶颈**:
- C 优化 memset (单线程 0.86%)，但主瓶颈已被 A 消除
- E 优化 I/O 量，但 DEEP10M 的瓶颈是 Recall 约束 (PQ 质量) 而非 I/O
- F 优化热向量命中，但 slot 架构和 WILLNEED_BG 都已触及天花板

**教训**: 优化方向的选择应基于 "瓶颈-收益" 比率，而非 "热点-修复" 直觉。
perf 显示的热点 (10.29% memset) 在分摊到单线程后 (0.86%) 不值得投入。

### 5.3 对未来 POC 的指导

1. **先量化单线程瓶颈占比**: 合计 X% ÷ 线程数 = 实际单线程 X/T%，<2% 不值得优化
2. **验证优化手段不竞争**: 新优化不应作用于已有优化手段的同一瓶颈
3. **评估规模外推性**: SIFT1M 的优化效果必须验证在 DEEP10M 下是否保持
4. **检查架构天花板**: 参数调优前先诊断架构上限 (如 FVC slot 命中率 ceiling)
5. **Recall 约束是硬约束**: PQ 质量到天花板后，I/O 优化无法转化为 QPS 提升

## 6. 拟新增条款

### DEC-097: multi-thread-scaling 方向 E/C/F 收益受限根因分析 {#DEC-097}
<!-- ndf: kind=decision status=stable date=2026-08-11 affects=multi-thread-scaling depends-on=DEC-072,DEC-073,DEC-074,DEC-070 source=observed -->

**Context.** multi-thread-scaling POC 6 个方向中，A (WILLNEED_BG) 大获成功 (+72.8%)，
B 已在 DEC-074 记录。C/E/F 虽有部分实验但收益受限或未执行，需归档根因分析。

**Decision.** 记录 C/E/F 收益受限的根因分析，作为未来优化方向选择的参考。

**Consequences.**
- 不改变任何现有条款或 Trunk 代码
- C2 (VL_POOL_THREADS) 已在 DEC-074 promote，本 DEC 仅补充分析
- F (FVC) 已在 DEC-073 promote，本 DEC 仅补充分析
- E (CSR 上磁盘) 确认为不执行方向，未来需产品需求驱动才重新评估

**Rejects**: multi-thread-scaling 方向 E (不执行确认)
