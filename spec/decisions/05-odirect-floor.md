# Decisions - O_DIRECT 地板 (DEC-057…061)

> 条款索引: `DEC-057`, `DEC-058`, `DEC-059`, `DEC-060`, `DEC-061`, `DEC-062`

## D-057: O_DIRECT 诚实基准测试 - Page Cache 加速比量化 {#DEC-057}
<!-- ndf: kind=decision date=2026-07-31 affects=DEC-039,CHR-006,CON-HONEST-002 source=observed -->
<!-- ndf: amended-by=DEC-059 -->

> **Amendment:** [[DEC-059]](2026-07-31)修正下文 §2 / §3 的叙事:
> 核心价值 = 内存节省 **+** 受限内存下的磁盘 I/O 优化能力;
> 「水分倍数」重新定位为 Layer2 对 Layer1 的 **page cache 加速比**(非虚假数字);
> page cache **不是免费资源**,与 RSS 共享 cgroup 预算。下文保留实测表为证据。

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
   O_DIRECT 地板有数量级加成(预算内合法)

2. **核心价值(经 DEC-059 修正)**: 内存节省 (271MB vs hnswlib 726MB) **+**
   在受限 cgroup 下优化真实磁盘 I/O 的能力。仅谈 QPS 优势在 page cache 耗尽时不成立

3. **Buffered 仍为生产默认**: page cache 在 **cgroup 预算内**(limit - RSS)合法使用,
   不是无限免费层。报告 MUST 按 CON-HONEST-002 标注模式

4. **O_DIRECT 单线程 130 QPS 对应 7.7ms/query**: I/O 主导 (100 候选 × 4KB 页
   × NVMe ~50-100μs/读)。这是性能地板, 无 page cache 补贴;战略定位见 [[DEC-059]]

5. **100M 规模的必要性确认**: 1M/10M 规模 page cache 可覆盖大部分 vecblocks
   (496MB/3.7GB)。100M 规模 vecblocks ~50GB, 覆盖率极低, O_DIRECT 成为必须路径

**Alternatives rejected.**
- 继续 only 报告 Buffered 数字: 违反 CON-HONEST-002 诚实协议
- 放弃 Buffered 模式: page cache 在预算内合法, 是生产优势
- 否认加速比: 数据清楚, 不诚实无意义

> rationale: 这不是"之前做错了", 而是测量维度的补全。Buffered 在 cgroup 内合法,
> O_DIRECT 揭示无缓存时的地板性能。两个数字都有价值, 缺一不可。
> DiskHNSW 的真正战场是 100M+ 规模, 那里 O_DIRECT 是多数真实路径([[DEC-059]])。

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
<!-- ndf: amended-by=DEC-062 -->

> **Amendment:** [[DEC-062]](2026-08-01) 修正下文「O_DIRECT = 优化第一优先级」叙事：
> **Buffered = 生产优化主目标**；O_DIRECT = 诚实验收地板 + 大规模必然磁盘 I/O 路径。
> cgroup 预算约束与双层机制仍有效；仅优先级/主战场表述被修订。

**Context.** DEC-057 完成了 O_DIRECT 诚实基准测试,量化了 Buffered 与 O_DIRECT
之间的性能差距(SIFT1M 17-19x, DEEP10M 9x)。DEC-030 将 page cache 定位为
"OS 免费的冷热分层",但未充分约束 page cache 在 cgroup 预算中的竞争关系。

用户校准(2026-07-31)明确了两个关键认知:

1. **Page cache 与 RSS 共享 cgroup 预算**:`memory.max ≥ RSS + page_cache`,
   两者竞争同一块内存。Page cache 不是"免费的白嫖",超了就是超了,一样被 OOM
   kill 或 reclaim。在运行过程中,加载的 page cache 不得使总内存超过 cgroup 限制。

2. **O_DIRECT 是诚实地板与必然 I/O 路径,不是诊断工具**（优先级叙事经 [[DEC-062]] 修正）:
   之前 DEC-030 将 O_DIRECT 定位为"诊断/测试模式"。重新校准后,O_DIRECT 代表
   真实磁盘 I/O 的性能地板。Page cache 在剩余预算内提供加速。
   **生产优化主目标**为 Buffered（逼近 hnswlib），见 [[DEC-062]]。

**可用 page cache 预算分析:**

| 规模 | cgroup | RSS | 可用 page cache | vecblocks 大小 | 可缓存比例 |
|------|--------|-----|----------------|---------------|-----------|
| SIFT1M | 512MB | 269MB | ~240MB | 496MB | ~48% |
| DEEP10M | 2GB | 1612MB | ~390MB | 3.7GB | ~10% |
| 100M (预估) | 4GB | ~2GB | ~2GB | ~50GB | ~4% |

随着规模增大,page cache 可缓存比例趋近于 0,O_DIRECT 路径成为绝大多数查询的
真实路径。

**Decision.**

1. **双层优化策略确立**（主战场经 [[DEC-062]] 修订）:
   - **Layer A (Buffered / page cache 主目标)**: 在 cgroup 预算内最大化有效命中与
     流水线，逼近 hnswlib（生产优化主战场）。
   - **Layer B (O_DIRECT 地板)**: 减少无效 I/O、I/O 与计算重叠等；抬高无缓存时的
     QPS 地板，并优化 miss 路径上的必然磁盘 I/O。
   - 两者叠加 = cgroup 限制下的最优性能；**不假设** Layer B 成果自动线性惠及 Layer A。

2. **修正 DEC-030 的 page cache 定位**:
   - DEC-030 第 1 点"page cache 是免费的"修正为"page cache 与匿名内存共享
     cgroup 预算,在预算内合法使用"
   - DEC-030 第 2 点"FINE_DIRECT 降级为诊断/测试模式"修正为"FINE_DIRECT
     是优化基座和性能地板,生产中与 Buffered 模式互补"
   - DEC-030 不再作为 I/O 真相源,O_DIRECT 的定位由本决策接管

3. **修正 DEC-057 的叙事**:
   - DEC-057 第 2 点"核心价值是内存节省而非 QPS 优势"方向正确但需补充:
     核心价值 = 内存节省 **+** 在受限内存下的磁盘 I/O 优化能力
   - DEC-057 的"水分倍数"重新定位为"page cache 加速比",即 Layer 2 对 Layer 1
     的加成倍数。不是"虚假数字",而是"缓存加速的真实效果"

4. **O_DIRECT 地板与 Buffered 主目标并行**（见 [[DEC-060]] / [[DEC-062]]）:
   - 当前 O_DIRECT SIFT1M 1T = 130 QPS (7.7ms/query),其中 ~100 次 4KB 随机读
   - 地板优化仍必要；生产路径上 Buffered 逼近 hnswlib 为 P3 主战场

**Alternatives rejected.**
- 继续将 O_DIRECT 视为诊断工具:低估了其在大规模场景的核心地位
- 放弃 Buffered 模式:page cache 在预算内仍是合法且有效的加速手段
- 将 page cache 视为免费资源:违反 cgroup v2 memory.max 同时限制 anon + file 的约束

> rationale: page cache 预算 = cgroup_limit - RSS，不是无限的；大规模下覆盖率趋近 0，
> O_DIRECT 成为多数真实 miss 路径。[[DEC-062]] 进一步明确：这不意味着生产优化应
> 以 O_DIRECT 为「第一优先级」——当前产品目标是在诚实预算下逼近全内存性能，
> 故 Buffered 为主战场，O_DIRECT 为地板与必然 I/O 路径。

---

## D-060: I/O 优化方案设计 - 减少 O_DIRECT 路径的磁盘 I/O 开销 {#DEC-060}
<!-- ndf: kind=decision date=2026-07-31 affects=DEC-009,DEC-017,DEC-018,DEC-030,DEC-059 source=deduced -->
<!-- ndf: amended-by=DEC-062 -->

**Context.** [[DEC-059]] 确立 O_DIRECT 诚实地板；[[DEC-062]] 明确 Buffered 为生产
优化主目标，O_DIRECT 为地板/必然 I/O 辅助路径。当前 O_DIRECT 性能:

| 规模 | 线程 | QPS | 延迟/query | I/O 量/query |
|------|------|-----|-----------|-------------|
| SIFT1M | 1T | 130 | 7.7ms | ~100×4KB = 400KB |
| SIFT1M | 4T | 502 | 8.0ms | ~100×4KB = 400KB |
| DEEP10M | 4T | 169 | 23.7ms | ~300×4KB = 1.2MB |

I/O 主导:SIFT1M 每次 query 读 ~100 个 4KB 页,NVMe 随机读 ~50-100μs/次,
总计 5-10ms。优化方向（经 [[DEC-061]] 修正）= **减少 I/O 数据量 / 候选数**、
**I/O 与计算重叠**，以及 **布局局部性**；不得默认「合并随机读以减少次数」。

**Decision.** 分 4 个优化方向；优先级以 [[DEC-061]] 后的现行排序为准：

### 方向 1: 候选页合并读取 (Read Coalescing) ❌ 已终止

**问题**: Fine Rerank 的 100 个候选分散在 ~100 个不同 4KB 页上,每页一次 pread。
但如果多个候选落在同一个 64KB block(16 页)内,可以一次读 64KB 而非 16×4KB。

**方案（历史）**:
1. 收集 Fine Rerank 候选的 page 号
2. 按 block_id 排序去重,合并同 block 的候选
3. 对密集 block(≥3 个候选在同 block)一次性读 64KB,在内存中提取所需 4KB 页
4. 对稀疏候选仍用 4KB pread

**初估收益（未兑现）**: 假设 30% 候选能合并,I/O 次数 100→~70,QPS +~30%。

**实现复杂度**: 中等。

**进展 / 终态 (2026-07-31)** — 见 [[DEC-061]]:
- **方向 1 已终止 ❌**: v1 pread +6–9%；v2 io_uring −10~16%。代码已回退；
  `BEH-017` / `API-009` / `CON-SLA-012` / `VER-017` / `DEF-019` 均为 deprecated。
- 根因: io_uring 批量并行已高效处理 4KB 随机读；合并引入冗余 I/O，收益为负。
- **现行最高优先级** → 方向 2 (I/O Pipelining)。
- 方向 3 降为「需重新证明」；方向 4 改为独立验证 Page Shuffle，不再依赖方向 1。

### 方向 2: I/O 与计算流水线 (I/O Pipelining) ★★★ 最高优先级

**问题**: 当前 Fine Rerank 是串行的:收集所有候选 -> 批量读 I/O -> 计算距离。
PQ 粗筛(Phase A)和 Fine Rerank(Phase B)完全串行。

**方案**:
1. Phase A 搜索过程中,当候选加入 result set 时,立即异步预取其 4KB 页
2. 利用 io_uring 提交预取,Phase A 继续图搜索
3. Phase B 开始时,部分候选的页已在 io_uring completion queue 中就绪
4. 实现 Phase A(CPU 密集)与 Fine Rerank I/O 的重叠

**预期收益**: 隐藏部分 I/O 延迟。SIFT1M Phase A ~0.5ms,Fine Rerank I/O ~7ms,
理想情况下可隐藏 0.5ms(~7% QPS 提升)。DEEP10M Phase A ~7ms,Fine Rerank I/O ~5ms,
重叠更多。

**实现复杂度**: 高。需要重构搜索流程,将 Phase A 和 Phase B 交错。

### 方向 3: 增大 I/O 粒度 (Adaptive Read Size) ⚠ 需重新证明

**问题**: 4KB 是最小页粒度;历史上假设「合并邻近页 → 更大读」可抬升有效带宽。

**方案（草案，与方向 1 机制同类）**:
1. 当连续候选的页地址接近时(差 < 64KB),合并为一次大读
2. 动态选择读粒度:4KB / 16KB / 64KB,基于候选密度
3. 读入的多余数据在内存中丢弃

**与 [[DEC-061]] 的关系**: 本方向与已终止的 Read Coalescing **共享「合并随机读」假设**。
在 io_uring + NVMe 上，方向 1 已证明冗余 I/O 常大于 SQE 减少收益。
因此方向 3 **不得默认排期实现**；仅当出现**新前提**（例如顺序友好布局、可证明冗余≈0、
或非 io_uring 路径的独立证据）时才重新开提案。

**初估收益（作废直至重测）**: +15-20% — 不得写入 must SLA。

### 方向 4: Page Shuffle 深度优化 (大规模验证) ★ 中优先级

**问题**: DEC-018 的 Page Shuffle 在 1M 规模收益边际(I/O 减 4%),
但在大规模(page cache 无法覆盖时)预期收益更大。

**方案**:
1. 在 O_DIRECT / 诚实协议下独立重测 Page Shuffle 的 QPS / I/O 足迹
2. **不再**以「提升 Read Coalescing 合并率」为理由（方向 1 已终止）
3. 在 DEEP10M + O_DIRECT 下验证；收益判据改为：更少唯一页触达、更低尾延迟、
   或与方向 2（流水线）的协同，而非 block 合并次数

**预期收益（修订）**: 页内邻居 co-locality 77.1% 可能降低有效随机页数；
幅度 TBD，须诚实测后写入 SLA。

**实现复杂度**: 低(已有 shuffle_vecblocks 工具,只需在 O_DIRECT 下重测)。

### 优化路线图（[[DEC-061]] 后）

| 阶段 | 优化 | 预期 QPS 提升 | 状态 |
|------|------|-------------|------|
| ~~P3.1~~ | ~~Read Coalescing~~ | ~~+30%~~ | **已终止**（[[DEC-061]]） |
| P3.2 | I/O Pipelining | +7-15%（初估） | **现行最高优先级** |
| P3.3 | Adaptive Read Size | TBD | ⚠ 与方向 1 同类；需新前提 |
| P3.4 | Page Shuffle + O_DIRECT | TBD | 独立验证，不绑方向 1 |
| **目标带** | | **aspirational 250–300** | 仅见愿景；非 must |

目标带仍为 O_DIRECT SIFT1M 1T 向 250–300 QPS 靠拢；**不得**把已终止的 P3.1
计入累计 must。

**Alternatives rejected.**
- SPDK 用户态 I/O:运维复杂度高,P3 阶段不引入(见 [[DEC-027]])
- mmap + userfaultfd:cgroup 限制下不稳定,且 O_DIRECT 与 mmap 互斥
- 全量预取所有 L0 向量:内存不够,违背磁盘搜索初衷
- **Read Coalescing（方向 1）**: 见 [[DEC-061]] 负结果

> rationale（修订）: 诚实 O_DIRECT 瓶颈是每 query ~100×4KB 的随机读足迹与串行
> Phase A→B。方向 1 证明「合并次数」在 io_uring+NVMe 上不成立。
> 后续应优先 **隐藏延迟（流水线）**、**减少需读的候选/页数**、以及 **布局局部性**；
> 任何「再合并大读」提案必须显式回答为何不会重蹈 [[DEC-061]]。
---

## D-061: Read Coalescing 负收益决策 - 方向 1 终止 {#DEC-061}
<!-- ndf: kind=decision date=2026-07-31 affects=DEC-060,BEH-017,API-009,CON-SLA-012,VER-017 source=observed -->

**Context.** DEC-060 方向 1 (Read Coalescing) 在两条 I/O 路径上实现并验证:

- **v1 (pread 路径)**: 候选页按 64KB block 分组,密集 block 一次 pread 64KB
- **v2 (io_uring 路径)**: 密集 block 提交 1 个 64KB SQE,替代多个 4KB SQE

**实测结果 (SIFT1M, 512MB cgroup, `FINE_DIRECT=1`, 1T):**

> **协议口径**: v1 表接近诚实 O_DIRECT / pread 慢路径（基线 ~60–130，与
> [[CON-SLA-011]] 同量级）。v2 表基线 ~802 QPS **显著高于** 诚实锚点 130 QPS，
> 视为**相对对比实验**（同配置开/关 coalescing），**不得**当作 Honest SoT 绝对值；
> 负号结论（coalesce 相对基线更差）仍成立。

### v1 pread 路径 (+6-9%, 低于预期)

| REFINE_EF | Recall | 基线 QPS | Coalesce QPS | 提升 |
|-----------|--------|---------|-------------|------|
| 200 | 97.20% | 60.9 | 66.5 | +9.2% |
| 100 | 95.75% | 110.9 | 118.2 | +6.6% |
| 80 | 94.90% | 133.3 | 141.6 | +6.2% |

### v2 io_uring 路径 (-10~16%, 负收益；相对对比)

| REFINE_EF | Threshold | Recall | 基线 QPS | Coalesce QPS | 变化 |
|-----------|-----------|--------|---------|-------------|------|
| 100 | 3 | 95.75% | 802.0 | 724.7 | **-9.6%** |
| 100 | 5 | 95.75% | 802.0 | 786.5 | -1.9% |
| 100 | 8 | 95.75% | 802.0 | 783.3 | -2.3% |
| 200 | 3 | 97.20% | 507.3 | 426.1 | **-16.0%** |

**Decision.**

1. **方向 1 (Read Coalescing) 终止**: v1 收益有限 (+6-9%) 且仅限 pread 慢路径,
   v2 在 io_uring 路径上负收益 (-10~16%)。代码已全部回退（`READ_COALESCE*` 删除）。
   pread 门控恢复为 `FINE_PREAD && !FINE_DIRECT`（O_DIRECT 走 io_uring 分支）；
   `FINE_DIRECT` 语义仍为 [[DEC-059]] 诚实地板，**不是** DEC-030「诊断」。

2. **根因记录**:
   - **v1 pread**: 逐页 syscall 开销主导, coalescing 减少调用次数但 pread 本身比 io_uring 慢约一个数量级
   - **v2 io_uring**: io_uring 批量并行提交已高效处理 4KB 随机读。NVMe 并行处理多 SQE,
     延迟 ≈ max(单次I/O延迟, 总数据量/带宽)。合并 64KB 读取引入冗余数据 (3 页 12KB 有效 -> 读 64KB),
     SQE 减少的收益 < 冗余 I/O 代价。threshold 越高退化越小, 但始终无正收益。

3. **条款状态更新**:
   - [[BEH-017]] / [[API-009]] / [[CON-SLA-012]] / [[VER-017]] / [[DEF-019]]: status=deprecated
   - 提案 `proposal-read-coalescing.md`、`proposal-read-coalescing-v2.md`:
     Status=**Rejected / Superseded by DEC-061**（历史记录，非 Pending）

4. **教训**:
   - io_uring 的批量提交已消除 syscall 开销, 在此基础上做 I/O 合并的收益为负
   - NVMe 的并行处理能力使 4KB 随机读的聚合带宽接近顺序读, "合并读取减少 I/O 次数" 的假设不成立
   - **O_DIRECT 地板优化的正确方向**: 减少 I/O 数据量 (如 PQ 精度提升减少候选数) 或
     I/O 与计算重叠 (方向 2: I/O Pipelining), 而非合并 I/O 粒度

5. **DEC-060 状态更新**:
   - 方向 1 → ❌ 已终止
   - 方向 2 → ★★★ 最高优先级
   - 方向 3 → ⚠ 与方向 1 同类，需新前提后才能再提案
   - 方向 4 → 独立验证 Page Shuffle，不绑方向 1

**Alternatives rejected.**
- 继续调参 threshold/size: v2 threshold=8 仍 -2.3%, 无正收益趋势
- 只保留 v1 pread 路径: pread 慢路径优化对地板无意义
- 换更大 block size (256KB): 冗余更多, 预期退化更严重

> rationale: 这是一个重要的负结果。它证明在 io_uring + NVMe 的组合下,
> 4KB 随机读已被高效并行化, 传统 "合并 I/O 减少次数" 的优化思路不适用。
> O_DIRECT 地板优化应转向减少 I/O 需求量 (更少候选/更小读取) 或隐藏 I/O 延迟 (流水线)。

---

## D-062: Buffered 为生产优化主目标 — 修正 DEC-059 优先级叙事 {#DEC-062}
<!-- ndf: kind=decision date=2026-08-01 affects=DEC-059,DEC-060,CHR-001,CHR-006,CON-HONEST-002,CON-SLA-013,BEH-021 source=deduced -->

**Context.** [[DEC-059]] 正确确立了：(1) page cache 与 RSS 共享 cgroup 预算；
(2) O_DIRECT 不是诊断玩具，而是诚实地板与大规模 miss 路径。但「O_DIRECT =
优化第一优先级」被过度解读：I/O Pipelining POC 与部分 SoT 条文把 O_DIRECT 当作
主优化战场，Buffered 沦为「page cache 已够、不必优化」的附属，偏离
[[CHR-001]]「在受限内存下逼近全内存 HNSW」的产品目标。

**Decision.**

1. **Buffered = 生产优化主目标**：默认路径 `FINE_BUFFERED=1`；在诚实 cgroup 预算内
   逼近 hnswlib；page cache 是合法核心加速层（非白嫖、非无限）。
2. **O_DIRECT = 诚实验收地板 + 必然磁盘 I/O 路径**：MUST 继续按 [[CON-HONEST-002]]
   报告；地板抬升与 miss 路径优化仍有独立价值；**不得**假设 O_DIRECT 收益线性惠及 Buffered。
3. **修正措辞**：CHR-001 / CHR-006 / CON-HONEST-002 / DEC-059 / DEC-060 中
   「优化第一优先级 / 优化优先级 = O_DIRECT」改为上述双定位；**不改** stable QPS 数字。
4. **POC 纪律**：`poc/io-pipelining/` 以 Buffered R0–R4 为主；O_DIRECT 为辅；
   v1 不可信数字 MUST NOT 引用（见 `proposal-goal-clarification` §7）。
5. **DEC-059 / DEC-060 仍有效**：预算约束、负结果（[[DEC-061]]）、方向 2 优先级不变；
   仅「谁是主战场」叙事被本决策接管。

**Alternatives rejected.**
- 废弃 O_DIRECT 优化：大规模 miss 路径仍需地板工程
- 保持「O_DIRECT 第一优先级」原文：与产品目标及已确认的 goal-clarification 冲突
- 立刻改写 stable SLA 数字：无新诚实证据；属 promote 闸门事项

> rationale: 诚实协议与优化主战场是两件事。O_DIRECT 回答「没有 page cache 时多快」；
> Buffered 回答「在合法预算内能否逼近全内存」。当前 1M/10M 产品验收与差距主要在后者。
