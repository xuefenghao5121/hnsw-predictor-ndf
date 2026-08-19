# Proposal: POC — 热点瓶颈画像 + 优化方向调研 (Profiling-Driven Optimization)

> track: poc
> Status: Implemented on 2026-08-18
> 日期: 2026-08-18
> Trunk SHA: a143392
> origin: human_intent
> Reviewed: 已审核 on 2026-08-18
> 关联: [[CHR-006]], [[CON-HONEST-002]], [[CON-SLA-014]], [[CON-SLA-019]], [[DEC-084]], [[DEC-070]], [[DEC-072]], [[DEC-073]], [[DEC-074]]

<!-- ndf:gate-slice begin=proposal_contract -->
## 0. 意图原文 (origin: human_intent)

> 直接先profilling我们目前的热点瓶颈，然后在网上搜索相关论文和解决方案，
> 给我一个proposal，我按照可行性来进行分析和建立POC

## 1. 结论先行

**当前头号热点是 Phase A 的 PQ 距离计算 `pqDistance`（约 37.9% CPU @4T）**，其本质是
**M=32 次查表 gather+add 的访存瓶颈**（距离表 32KB，随机访存）。其次是多线程下的
**VisitedList memset（5.4%→10.3%）** 与 **WILLNEED 内核锁竞争（6.27% @12T）**。

本提案按「可行性 × 收益 × 风险」排序给出 4 个 POC 方向，供你按可行性挑选落地：

| 方向 | 目标热点 | 可行性 | 收益 | 风险 |
|------|---------|--------|------|------|
| **D1 PQ 距离 SIMD 化 (FastScan/QuickerADC)** | pqDistance 37.9% | ★★★ 高 | 中-高 | 低（不改召回） |
| **D2 RaBitQ 二进制量化** | PQ 计算 + 内存 | ★★ 中 | 高 | 中（需重量化+图兼容验证） |
| D3 VisitedList 池化 + WILLNEED 自适应 | memset 10.3% + 锁 6.27% | ★★★ 高 | 低-中 | 低 |
| D4 候选数再压缩 | I/O + PQ 总量 | ★ 低（近天花板） | 低 | 高（recall 已卡 95%） |

## 2. 当前热点瓶颈画像（源自现有 evidence，非本次新采集）

### 2.1 CPU 热点（SIFT1M, perf record --call-graph dwarf, CON-SLA-014）

来源：`poc/multi-thread-scaling/ndf/evidence/bottleneck-profiling-20260805.md`

| 热点 | 4T | 12T | 定性 |
|------|-----|-----|------|
| **pqDistance (PQ ADC 查表)** | **37.90%** | 20.73% | 头号 CPU 热点（单线程/低并发主导） |
| VisitedList memset | 5.38% | **10.29%** | cache line bouncing，随线程数翻倍 |
| posix_fadvise(WILLNEED) 内核锁 | 0% | **6.27%** | osq_lock/rwsem/queued_spin_lock |
| searchLayer0 | 20.66% | 9.62% | 占比下降（非瓶颈） |
| pthread_mutex (BlockCache LRU) | 1.51% | 0% | **不是瓶颈** |

### 2.2 `pqDistance` 实现现状（src/core/disk_hnsw.cpp:298）

已做：每 query 用 SIMD（AVX2/NEON，simd.h）预计算 `pq_dist_table_ [M×ksub]`，
`pqDistance` 退化为 M=32 次 `t[m*ksub + code[m]]` 查表 + 4 路标量累加。

**剩余热点根因**：32 次对 32KB 表的**随机 gather**（`code[m]` 每元素随机），
非连续访存 → 即便表 fit L1/L2，随机访问仍产生 cache miss 与依赖链，
是典型**访存受限（memory-bound）**而非纯计算受限。

### 2.3 诚实 sustained 下的定位（[[DEC-084]]）

诚实测量（禁预热）后，DiskHNSW 相对 hnswlib 的通量仅 ~16–33%（512MB 16T 6,694
vs 42,947 QPS），**I/O bound 是宏观主因**；pqDistance 是 I/O 之外最大的可优化 CPU 项。
ADAPTIVE_EF（+12.5~31.4%）与 GBDT-v2（+12.3~47.4%）已覆盖「候选数自适应剪枝」，
故剩余可挖点在**单次距离计算更快**与**候选/访存更少**两条线。

## 3. 业界方案调研（web 检索，非训练记忆）

### 3.1 PQ 距离计算 SIMD 加速

- **QuickerADC**（André, Kermarrec, Douze, arXiv:1812.09162）：用 SIMD 解锁 PQ 的
  ADC 距离计算潜力，报告显著加速；社区实现含 AVX-512 变体。
  - https://arxiv.org/pdf/1812.09162v2
  - https://github.com/nlescoua/faiss-quickeradc
- **PQ FastScan**（FAISS）：用 SIMD 字节 shuffle（`vpshufb`/`pshufb`，ARM `vqtbl1q_u8`）
  一次 gather 16 字节、批量算多个距离，把 M 次标量查表换成寄存器内 shuffle。
  - https://github.com/nlescoua/faiss-quickeradc （FastScan 相关实现参考）
  - Rust 侧等价实践（NEON `vqtbl1q_u8`）：https://gist.github.com/CrossGen-ai/a4e2241217547e9d23e76ce905c4b99c

### 3.2 二进制量化替代 PQ

- **RaBitQ**（Gao & Long, SIGMOD 2024, arXiv:2405.12497）：随机旋转 + 1-bit 量化，
  有理论误差界；距离退化为**位运算/近似**，比 SIMD-PQ 更快、内存更省；论文称在
  IVF 上 recall 不弱于 PQ。
  - https://arxiv.org/abs/2405.12497
  - https://github.com/gaoj0017/RaBitQ
  - ⚠️ 风险提示：本仓历史上 OPQ 旋转与 HNSW 图**不兼容**（[[DEC-072]] 记录：旋转空间
    改变邻居排序，图遍历走错方向）。RaBitQ 同属「旋转 + 量化」，MUST 先验证其
    随机旋转与 HNSW 图遍历的兼容性，否则重蹈 OPQ 覆辙。

### 3.3 其他（列为备选，不主推）

- Additive Quantization / LSQ（Learned Structured Quantization）：精度更好但索引/查询
  更重，与「低延迟查表」目标相悖，暂列备选。
- DiskANN beam search：通过小 beam 减少 SSD 读次数（I/O 线），本仓已有
  ADAPTIVE_EF/GBDT 剪枝，方向重叠，暂列备选。

> ⚠️ 以上均为公开文献/实现，**非本仓实测**；不构成新 SLA，不得写成 must 契约。

## 4. POC 方向排序（供可行性分析）

### D1 — pqDistance SIMD 化 / FastScan 式批量查表（推荐优先）
- **目标**：37.9% CPU 热点；不改召回（距离数值完全一致）。
- **做法**：把 M=32 次标量 `t[m*ksub+code[m]]` 改为 SIMD 字节 shuffle + 批量累加
  （AVX2 `vpshufb` 或 `_mm256_i32gather_ps`），一次处理 8/16 个 m。
- **预期**：pqDistance 本身 2–4x，端到端 QPS 提升受 I/O 占比上限约束（4T 场景最受益）。
- **风险**：低；x86 AVX2 已具备（charter Non-Goals 明确 x86 AVX2 依赖）。

### D2 — RaBitQ 二进制量化（若 D1 到顶后）
- **目标**：把 PQ 距离换成 1-bit 码的 popcount/位运算距离，进一步降计算与内存。
- **风险**：中；必须先验证随机旋转与 HNSW 图兼容（OPQ 前车之鉴 [[DEC-072]]）。
- **门禁**：R0 只做「旋转 + 1-bit 码」下 recall 是否 ≥95% 的可行性判定，不先改 Trunk。

### D3 — VisitedList 池化 + WILLNEED 自适应（低复杂度收尾）
- 已记录方向（bottleneck-profiling 的方向 A/B/C）：thread_local VisitedList 池复用、
  `NUM_THREADS≥8` 时自适应禁用 WILLNEED。收益低-中，但实现快，可作 D1 的并行走量。

### D4 — 候选数再压缩（不推荐，近天花板）
- [[DEC-072]] 已证 recall≥95% 下 EF=300 + M=32 是硬约束；M=24 / EF 降低均跌破 95%。
  除非放宽 SLA（另开 process 提案），否则无空间。

## 5. 非目标 / 约束

- 本提案仅「画像 + 调研 + 方向排序」，**不落地任何 Trunk 条款**（不新增 DEC/SLA/must，
  不写 spec/meta 正文，不写 src/include/tests）。
- 不改 [[CHR-006]] Recall@10 ≥ 95% 门槛；D1 严格要求距离数值不变、recall 不变。
- 所有 POC 验证 MUST 沿用 [[CON-SLA-019]] 禁预热 + [[CON-SLA-020]] sustained 基线 +
  [[CON-SLA-014]] 严格隔离，避免重蹈 [[DEC-084]] 的 cache-warmed 假象。
- 已确认后落地提案与 TOPIC 装订器；停在「已审核」。不 approve、不 forge approved_by。不写 DESIGN，直到提案审核通过后走 TOPIC已审核。

## 6. 参考资料

- 瓶颈画像：`poc/multi-thread-scaling/ndf/evidence/bottleneck-profiling-20260805.md`
- QuickerADC：https://arxiv.org/pdf/1812.09162v2 · https://github.com/nlescoua/faiss-quickeradc
- PQ FastScan（SIMD shuffle）：https://gist.github.com/CrossGen-ai/a4e2241217547e9d23e76ce905c4b99c
- RaBitQ：https://arxiv.org/abs/2405.12497 · https://github.com/gaoj0017/RaBitQ
- OPQ 与 HNSW 不兼容教训：[[DEC-072]]（`poc/pq-quality/NOTES.md`）
<!-- ndf:gate-slice end=proposal_contract -->

---

提案已落地：`spec/open/proposal-poc-hotspot-optimization.md`（Implemented on 2026-08-18）。
装订器：`poc/hotspot-optimization/ndf/TOPIC.md`。未写 DESIGN、未落地 Trunk 条款。
产品提案已审核（已审核）。下一步请审阅 TOPIC，回复「TOPIC已审核」。
