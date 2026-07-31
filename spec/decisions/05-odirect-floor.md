# Decisions — O_DIRECT 地板 (DEC-057…060)

> 条款索引: `DEC-057`, `DEC-058`, `DEC-059`, `DEC-060`

## D-057: O_DIRECT 诚实基准测试 - Page Cache 加速比量化 {#DEC-057}
<!-- ndf: kind=decision date=2026-07-31 affects=DEC-039,CHR-006,CON-HONEST-002 source=observed -->
<!-- ndf: amended-by=DEC-059 -->

> **Amendment:** [[DEC-059]]（2026-07-31）修正下文 §2 / §3 的叙事：
> 核心价值 = 内存节省 **+** 受限内存下的磁盘 I/O 优化能力；
> 「水分倍数」重新定位为 Layer2 对 Layer1 的 **page cache 加速比**（非虚假数字）；
> page cache **不是免费资源**，与 RSS 共享 cgroup 预算。下文保留实测表为证据。

**Context.** DEC-039 确立了诚实协议 (drop_caches + posix_fadvise), 但只解决查询间
page cache 复用。CON-HONEST-002 要求同时报告 Buffered 和 O_DIRECT 两组数字。
本决策记录 O_DIRECT 模式下的实测结果, 量化 page cache 相对 O_DIRECT 地板的加速比。

**Bug 修复**: O_DIRECT + FINE_PREAD 组合下, pread 路径的 `std::make_unique<char[]>`
buffer 不满足 O_DIRECT 的 512 字节对齐要求。改用 `posix_memalign` + 自定义
`AlignedBuf` 结构修复。

**实测结果:**

### SIFT1M (512MB cgroup)

| 模式 | 线程 | Recall | QPS | RSS | 加速比 (Buffered/Direct) |
|------|------|--------|-----|-----|-------------------------|
| Buffered | 1T | 95.70% | 2450 | 271MB | 基线 |
| O_DIRECT | 1T | 95.70% | 130 | 271MB | **18.8x** |
| Buffered | 4T | 95.70% | 8312 | 277MB | 基线 |
| O_DIRECT | 4T | 95.70% | 502 | 277MB | **16.6x** |

### DEEP10M (3GB cgroup, 4T)

| 模式 | Recall | QPS | RSS | 加速比 |
|------|--------|-----|-----|--------|
| Buffered | 95.15% | 1535 | 2502MB | 基线 |
| O_DIRECT | 95.15% | 169 | 2502MB | **9.1x** |

**Decision.**

1. **确认 page cache 加速比**: SIFT1M 17-19x, DEEP10M 9x。Buffered QPS 相对
   O_DIRECT 地板有数量级加成（预算内合法）

2. **核心价值（经 DEC-059 修正）**: 内存节省 (271MB vs hnswlib 726MB) **+**
   在受限 cgroup 下优化真实磁盘 I/O 的能力。仅谈 QPS 优势在 page cache 耗尽时不成立

3. **Buffered 仍为生产默认**: page cache 在 **cgroup 预算内**（limit − RSS）合法使用，
   不是无限免费层。报告 MUST 按 CON-HONEST-002 标注模式

4. **O_DIRECT 单线程 130 QPS 对应 7.7ms/query**: I/O 主导 (100 候选 × 4KB 页
   × NVMe ~50-100μs/读)。这是性能地板, 无 page cache 补贴；战略定位见 [[DEC-059]]

5. **100M 规模的必要性确认**: 1M/10M 规模 page cache 可覆盖大部分 vecblocks
   (496MB/3.7GB)。100M 规模 vecblocks ~50GB, 覆盖率极低, O_DIRECT 成为必须路径

**Alternatives rejected.**
- 继续 only 报告 Buffered 数字: 违反 CON-HONEST-002 诚实协议
- 放弃 Buffered 模式: page cache 在预算内合法, 是生产优势
- 否认加速比: 数据清楚, 不诚实无意义

> rationale: 这不是"之前做错了", 而是测量维度的补全。Buffered 在 cgroup 内合法,
> O_DIRECT 揭示无缓存时的地板性能。两个数字都有价值, 缺一不可。
> DiskHNSW 的真正战场是 100M+ 规模, 那里 O_DIRECT 是多数真实路径（[[DEC-059]]）。

---

## D-058: O_DIRECT + pread buffer 对齐 bug 修复 {#DEC-058}
<!-- ndf: kind=decision date=2026-07-31 affects=DEC-030 source=observed -->

**Context.** `FINE_DIRECT=1 FINE_PREAD=1` 组合下, pread 路径使用
`std::make_unique<char[]>(read_bytes)` 分配缓冲区。O_DIRECT 要求缓冲区地址
对齐到 512 字节 (或 block size), 但 `new char[]` 只保证 `alignof(max_align_t)`
(通常 16 字节) 对齐。

**Bug 影响:** `FINE_DIRECT=1 FINE_PREAD=1` 运行时 pread 返回 EINVAL (-1),
候选向量全部丢失, recall 崩到 0%。当前无人触发此组合, bug 未暴露。

**修复:** 引入 `AlignedBuf` 结构, 使用 `posix_memalign(&ptr, 4096, size)` 分配,
4096 对齐满足所有 O_DIRECT 要求。同时为 `unordered_map` 兼容性添加默认构造函数。

**验证:** SIFT1M O_DIRECT 1T recall 95.70% (与 Buffered 一致), 确认 bug 已修复。

---

## D-059: 战略重新校准 - O_DIRECT 地板优化 + Page Cache 受限加速 {#DEC-059}
<!-- ndf: kind=decision date=2026-07-31 affects=CHR-001,CHR-004,CHR-006,DEC-030,DEC-057,CON-HONEST-002 source=deduced -->

**Context.** DEC-057 完成了 O_DIRECT 诚实基准测试，量化了 Buffered 与 O_DIRECT
之间的性能差距（SIFT1M 17-19x, DEEP10M 9x）。DEC-030 将 page cache 定位为
"OS 免费的冷热分层"，但未充分约束 page cache 在 cgroup 预算中的竞争关系。

用户校准（2026-07-31）明确了两个关键认知：

1. **Page cache 与 RSS 共享 cgroup 预算**：`memory.max ≥ RSS + page_cache`，
   两者竞争同一块内存。Page cache 不是"免费的白嫖"，超了就是超了，一样被 OOM
   kill 或 reclaim。在运行过程中，加载的 page cache 不得使总内存超过 cgroup 限制。

2. **O_DIRECT 是优化基座，不是诊断工具**：之前 DEC-030 将 O_DIRECT 定位为
   "诊断/测试模式"。重新校准后，O_DIRECT 代表真实磁盘 I/O 的性能地板，
   是优化的第一优先级。Page cache 在剩余预算内提供有限加速，是第二层。

**可用 page cache 预算分析:**

| 规模 | cgroup | RSS | 可用 page cache | vecblocks 大小 | 可缓存比例 |
|------|--------|-----|----------------|---------------|-----------|
| SIFT1M | 512MB | 269MB | ~240MB | 496MB | ~48% |
| DEEP10M | 2GB | 1612MB | ~390MB | 3.7GB | ~10% |
| 100M (预估) | 4GB | ~2GB | ~2GB | ~50GB | ~4% |

随着规模增大，page cache 可缓存比例趋近于 0，O_DIRECT 路径成为绝大多数查询的
真实路径。

**Decision.**

1. **双层优化策略确立**：
   - **Layer 1 (O_DIRECT 地板优化)**：减少 I/O 次数、增大 I/O 粒度、批量化、
     I/O 与计算重叠。目标是抬高无缓存时的 QPS 地板。
   - **Layer 2 (Page Cache 受限加速)**：在 cgroup 预算内自然填充 page cache，
     热数据自动被缓存。但可用预算有限，不能作为性能基座。
   - Layer 1 是地基，Layer 2 是有限加成。两者叠加 = cgroup 限制下的最优性能。

2. **修正 DEC-030 的 page cache 定位**：
   - DEC-030 第 1 点"page cache 是免费的"修正为"page cache 与匿名内存共享
     cgroup 预算，在预算内合法使用"
   - DEC-030 第 2 点"FINE_DIRECT 降级为诊断/测试模式"修正为"FINE_DIRECT
     是优化基座和性能地板，生产中与 Buffered 模式互补"
   - DEC-030 不再作为 I/O 真相源，O_DIRECT 的定位由本决策接管

3. **修正 DEC-057 的叙事**：
   - DEC-057 第 2 点"核心价值是内存节省而非 QPS 优势"方向正确但需补充：
     核心价值 = 内存节省 **+** 在受限内存下的磁盘 I/O 优化能力
   - DEC-057 的"水分倍数"重新定位为"page cache 加速比"，即 Layer 2 对 Layer 1
     的加成倍数。不是"虚假数字"，而是"缓存加速的真实效果"

4. **O_DIRECT 优化成为 P3 之前的核心工作**：
   - 当前 O_DIRECT SIFT1M 1T = 130 QPS (7.7ms/query)，其中 ~100 次 4KB 随机读
   - 优化目标：在不改变 recall 的前提下，将单查询 I/O 次数减半或 I/O 粒度增大
   - 具体方案见 [[DEC-060]]

**Alternatives rejected.**
- 继续将 O_DIRECT 视为诊断工具：低估了其在大规模场景的核心地位
- 放弃 Buffered 模式：page cache 在预算内仍是合法且有效的加速手段
- 将 page cache 视为免费资源：违反 cgroup v2 memory.max 同时限制 anon + file 的约束

> rationale: 之前将 O_DIRECT 定位为"诚实基准/诊断工具"，是因为在 1M/10M 规模
> page cache 可覆盖大部分 vecblocks，O_DIRECT 似乎只是"最差情况"。
> 但用户校准揭示了一个更本质的事实：page cache 预算 = cgroup_limit - RSS，
> 它不是无限的。随着规模增大，这个预算对 vecblocks 的覆盖率趋近于 0。
> O_DIRECT 不是"最差情况"，而是"大多数情况"。因此 O_DIRECT 优化是性能基座，
> page cache 是在基座之上的有限加成。

---

## D-060: I/O 优化方案设计 - 减少 O_DIRECT 路径的磁盘 I/O 开销 {#DEC-060}
<!-- ndf: kind=decision date=2026-07-31 affects=DEC-009,DEC-017,DEC-018,DEC-030,DEC-059 source=deduced -->

**Context.** [[DEC-059]] 确立 O_DIRECT 地板优化为第一优先级。当前 O_DIRECT 性能：

| 规模 | 线程 | QPS | 延迟/query | I/O 量/query |
|------|------|-----|-----------|-------------|
| SIFT1M | 1T | 130 | 7.7ms | ~100×4KB = 400KB |
| SIFT1M | 4T | 502 | 8.0ms | ~100×4KB = 400KB |
| DEEP10M | 4T | 169 | 23.7ms | ~300×4KB = 1.2MB |

I/O 主导：SIFT1M 每次 query 读 ~100 个 4KB 页，NVMe 随机读 ~50-100μs/次，
总计 5-10ms。优化方向 = **减少 I/O 次数** 和 **改善 I/O 模式**。

**Decision.** 分 4 个优化方向，按投入产出比排序：

### 方向 1: 候选页合并读取 (Read Coalescing) ★★★ 最高优先级

**问题**: Fine Rerank 的 100 个候选分散在 ~100 个不同 4KB 页上，每页一次 pread。
但如果多个候选落在同一个 64KB block（16 页）内，可以一次读 64KB 而非 16×4KB。

**方案**:
1. 收集 Fine Rerank 候选的 page 号
2. 按 block_id 排序去重，合并同 block 的候选
3. 对密集 block（≥3 个候选在同 block）一次性读 64KB，在内存中提取所需 4KB 页
4. 对稀疏候选仍用 4KB pread

**预期收益**: 假设 30% 的候选能合并（BFS 重排后的局部性），I/O 次数从 100 -> ~70，
QPS 提升 ~30%。

**实现复杂度**: 中等。需修改 Fine Rerank 路径，增加候选排序和合并逻辑。

### 方向 2: I/O 与计算流水线 (I/O Pipelining) ★★ 高优先级

**问题**: 当前 Fine Rerank 是串行的：收集所有候选 -> 批量读 I/O -> 计算距离。
PQ 粗筛（Phase A）和 Fine Rerank（Phase B）完全串行。

**方案**:
1. Phase A 搜索过程中，当候选加入 result set 时，立即异步预取其 4KB 页
2. 利用 io_uring 提交预取，Phase A 继续图搜索
3. Phase B 开始时，部分候选的页已在 io_uring completion queue 中就绪
4. 实现 Phase A（CPU 密集）与 Fine Rerank I/O 的重叠

**预期收益**: 隐藏部分 I/O 延迟。SIFT1M Phase A ~0.5ms，Fine Rerank I/O ~7ms，
理想情况下可隐藏 0.5ms（~7% QPS 提升）。DEEP10M Phase A ~7ms，Fine Rerank I/O ~5ms，
重叠更多。

**实现复杂度**: 高。需要重构搜索流程，将 Phase A 和 Phase B 交错。

### 方向 3: 增大 I/O 粒度 (Adaptive Read Size) ★ 中优先级

**问题**: 4KB 是最小页粒度，但 NVMe 对 4KB 随机读的 IOPS 利用率低
（NVMe 可达 500K IOPS @4KB，但每次 syscall 开销 ~2-3μs，实际有效 IOPS ~200K）。

**方案**:
1. 当连续候选的页地址接近时（差 < 64KB），合并为一次大读
2. 动态选择读粒度：4KB / 16KB / 64KB，基于候选密度
3. 读入的多余数据在内存中丢弃（类似 Page Search 的思路）

**预期收益**: 减少 syscall 次数。100 次 4KB -> ~50 次（4KB + 16KB 混合），
QPS 提升 ~15-20%。

**实现复杂度**: 中等。需要动态 I/O 粒度选择逻辑。

### 方向 4: Page Shuffle 深度优化 (大规模验证) ★ 中优先级

**问题**: DEC-018 的 Page Shuffle 在 1M 规模收益边际（I/O 减 4%），
但在大规模（page cache 无法覆盖时）预期收益更大。

**方案**:
1. 在 O_DIRECT 模式下重新评估 Page Shuffle 的收益
2. 结合方向 1（Read Coalescing），Page Shuffle 提升同 block 候选密度
3. 在 DEEP10M + O_DIRECT 下验证

**预期收益**: Page Shuffle 提升页内邻居 co-locality 到 77.1%，直接提升方向 1 的
合并率。两者协同可能将 I/O 次数从 100 -> ~50。

**实现复杂度**: 低（已有 shuffle_vecblocks 工具，只需在 O_DIRECT 下重测）。

### 优化路线图

| 阶段 | 优化 | 预期 QPS 提升 | 实现周期 |
|------|------|-------------|--------|
| P3.1 | Read Coalescing | +30% (130->170) | 1-2 周 |
| P3.2 | I/O Pipelining | +7-15% | 2-3 周 |
| P3.3 | Adaptive Read Size | +15-20% | 1 周 |
| P3.4 | Page Shuffle + O_DIRECT 验证 | 协同 +10-20% | 3 天 |
| **累计** | | **130 -> ~250-300 QPS** | |

目标：O_DIRECT SIFT1M 1T 从 130 QPS 提升到 250-300 QPS，缩小与 Buffered 的差距。

**Alternatives rejected.**
- SPDK 用户态 I/O：运维复杂度高，P3 阶段不引入（见 [[DEC-027]]）
- mmap + userfaultfd：cgroup 限制下不稳定，且 O_DIRECT 与 mmap 互斥
- 全量预取所有 L0 向量：内存不够，违背磁盘搜索初衷

> rationale: O_DIRECT 130 QPS 的瓶颈是 I/O 次数（100 次随机 4KB 读），
> 不是单次 I/O 延迟。减少 I/O 次数的最有效手段是合并读取和流水线。
> Page Shuffle（DEC-018）在 O_DIRECT 模式下可能从"边际收益"变成"显著收益"，
> 因为它直接提升了 Read Coalescing 的合并率。四个方向协同作用，
> 而非独立优化。
