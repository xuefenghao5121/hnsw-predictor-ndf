# Behavior - 搜索路径

> 条款索引: `BEH-001`, `BEH-002`, `BEH-003`, `BEH-004`, `BEH-005`, `BEH-006`, `BEH-008`, `BEH-021`(deprecated), `BEH-022`(deprecated), `BEH-023`(deprecated), `BEH-024`(stable, model=MODEL-WILLNEED-001), `BEH-033`(stable), `BEH-034`(stable)

## 搜索流程状态机 {#BEH-001}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

DiskHNSW 搜索 MUST 遵循以下状态转移:

```
[查询到达] → Phase0: greedyDescent (L_high → L1)
           → PhaseA: searchLayer0 (PQ ADC, ef=REFINE_EF or ef_search)
           → PhaseB: FineRerank (4KB page reads, exact L2)
           → [返回 top-K]
```

**Phase B 精排子状态机** (from `disk_hnsw.cpp:1688-1913`):

```
[Phase A 候选] → 遍历候选
  ├─ cache hit (block cache or flat_vec_cache) → 立即算 L2 → consider()
  └─ cache miss
       ├─ FINE_PREAD=1 → pread 批量 4KB 读 → consider() + putFlatVector()
       └─ FINE_PREAD=0 → io_uring 批量提交 4KB 读
            ├─ FINE_MERGE=1 → 合并相邻页 8KB
            └─ FINE_MERGE=0 → 单页 4096B
            → waitCompletion + reap → consider() + putFlatVector()
```

## 搜索模式分支 {#BEH-002}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

`searchKnn()` 在 `disk_hnsw.cpp:1601` 中 MUST 根据环境变量选择搜索策略:

| 环境变量 | 模式 | 函数 |
|----------|------|------|
| `TWO_STAGE=1` + PQ | 两阶段搜索 | `searchLayer0()` (ef=REFINE_EF) → FineRerank |
| `BEAM_WIDTH>0` | Beam search | `searchLayer0Beam()` |
| `NONBLOCK=1` | 非阻塞 I/O overlap | `searchLayer0NonBlocking()` |
| `BATCH_IO_N>0` | 批量并行 I/O | `searchLayer0BatchIO()` |
| 默认 | 标准 best-first | `searchLayer0()` (ef=ef_search) |

## Layer 0 搜索核心循环 {#BEH-003}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-001 -->

所有 `searchLayer0*` 变体 MUST 使用相同的核心循环结构(`disk_hnsw.cpp:390-820`):

```
while candidate_set not empty:
  pop candidate with min distance
  if candidateDist > lowerBound AND |top_candidates| == ef: break
  获取邻居列表 (CSR in-mem > CachedBlock)
  对每个未访问邻居:
    ├─ PQ mode → pqDistance() (ADC 查表)
    ├─ PQ_HYBRID=1 + cache hit → exact L2
    ├─ in-cache → exact L2
    └─ miss → pending list → batch wait I/O → exact L2
    如果距离 < lowerBound 或 |top_candidates| < ef:
      加入 candidate_set 和 top_candidates
      更新 lowerBound = top_candidates.top().first
```

## 贪心下降 {#BEH-004}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-001 -->

`greedyDescent()` (`disk_hnsw.cpp:343-384`) MUST:
1. 从 `entry_point` 开始,从 `max_level` 向下到 Layer 1
2. 每层:遍历当前节点在该层的邻居,如果找到更近的邻居就移动过去
3. 重复直到在当前层没有更近的邻居
4. 完全在内存中操作(上层向量 + 上层邻接表),零 I/O

## PQ 距离计算 {#BEH-005}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-001 -->

`pqDistance()` (`disk_hnsw.cpp:301-337`) MUST 分两条路径:

1. **查表快路径**(`pq_dist_table_` 非空时):
   - 展开循环 4 路并行(m+0..m+3 同时查表累加)
   - 退化为 `M * ksub` 表查值 + 加法

2. **ADC fallback**(距离表未构建时):
   - 直接计算 `|query_sub - centroid|2`
   - 每个子向量独立计算后累加

## PQ 距离表构建 {#BEH-006}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-005 -->

`buildPqDistTable()` (`disk_hnsw.cpp:244-299`) MUST 分支:
- **`dsub == 4`**: AVX2 路径,一次处理 2 个 centroid (8 floats),用 `_mm256_sub_ps` + `_mm256_mul_ps` + `_mm_hadd_ps` 水平加法
- **`dsub != 4`**: 标量路径,三重循环 (M × ksub × dsub)
- 结果存入 **thread_local** `pq_dist_table_`,保证多线程安全

## I/O Pipelining 行为 (探索轨) {#BEH-021}
<!-- ndf: kind=req level=tbd layer=L1 status=deprecated since=0.8 source=deduced topic=io-pipelining -->
<!-- ndf: refines=BEH-001 depends-on=DEC-060,DEC-062,API-010,CON-POC-001 deprecated-by=DEC-071 -->

> **track: poc | status: draft | topic: io-pipelining**
> 装订器: `poc/io-pipelining/ndf/TOPIC.md`;提案 `spec/open/proposal-io-pipelining.md`(Active)。
> 不得作为生产默认;不纳入 stable must SLA([[CON-POC-001]])。关闭主题前勿改 stable / `src/`。

当 `PIPE_FINE=1` 时,`searchLayer0()` 在候选加入 `top_candidates` 时,拟 MUST 异步提交
对应 4KB vecblocks 页的 io_uring 读取到独立 pipeline ring(`pipe_ring_`)。
**两种 I/O 模式(O_DIRECT / Buffered)均启用。** 按 [[DEC-062]],Buffered 为主验证路径。

**L1 草案契约**:
1. 预取触发:邻居节点加入 `top_candidates` 且 rank ≤ `PIPE_THRESHOLD` 时提交
2. 去重:同一页不重复提交
3. 独立 io_uring 实例:`pipe_ring_` 与 `vec_ring_` 分离,避免 SQE/CQE 竞争
4. Phase B 对接:先 reap `pipe_ring_` 已就绪页 (L5),再查 page cache (L4),最后 vec_ring_ 原路径
5. `PIPE_FINE=0`(默认)时拟 MUST 零开销,行为与基线完全一致
6. 跨页向量:cross-page 候选需提交 page0 和 page0+1 两个 SQE
7. Buffered 模式下 pipe_ring_ 读取自然填充 L4 (page cache),提供跨 query 缓存

**Buffered 模式下 pipe_ring_ 的核心价值**:主动填充 L4(page cache),而非仅「绕过 L4」。
pipe_ring_ 的 Buffered I/O 将即将需要的候选页提前拉入有限的 page cache 预算,
减少 Phase B 中 page cache miss 导致的磁盘 I/O 等待([[DEC-062]])。

> rationale: Phase A (CPU 密集) 与 Fine Rerank I/O 当前完全串行。pipe_ring_ 是
> Phase A 期间 I/O 与 CPU 并行的唯一主动机制,两种模式都必须保留。
> 与 [[DEC-061]] 的 Read Coalescing 不同--不改 I/O 粒度/次数,仅让 I/O 与 CPU 并行。
> 系统优化不是非此即彼,而是彼此依赖的层叠结构:L5 (pipe_ring_) → L4 (page cache)
> → L1/L2/L3 (CPU cache) 协作,不分模式分治。

## L1/L2/L3 CPU Cache 向量预取 (探索轨) {#BEH-022}
<!-- ndf: kind=req level=tbd layer=L1 status=deprecated since=0.8 source=deduced topic=io-pipelining -->
<!-- ndf: refines=BEH-021 depends-on=API-010 deprecated-by=DEC-071 -->

> **track: poc | status: draft | topic: io-pipelining**
> 装订器: `poc/io-pipelining/ndf/TOPIC.md`;提案 `spec/open/proposal-io-pipelining.md`。

当 `PIPE_L1=1` 时,Phase B 遍历候选前拟 MUST 对下一个候选的向量地址执行 `_mm_prefetch`,
将其预取到 L1/L2/L3 CPU cache。预取粒度 = `ceil(dim * sizeof(float) / 64)` 条 cache line。

> rationale: 数据无论来自 L5 (pipe_ring_) 还是 L4 (page cache),距离计算前
> 都可以 `_mm_prefetch` 到 CPU cache,消除 L2 miss stall。

## L4 Page Cache 旁路填充 (探索轨) {#BEH-023}
<!-- ndf: kind=req level=tbd layer=L1 status=deprecated since=0.8 source=deduced topic=io-pipelining -->
<!-- ndf: refines=BEH-021 depends-on=API-010 deprecated-by=DEC-071 -->

> **track: poc | status: draft | topic: io-pipelining**
> 装订器: `poc/io-pipelining/ndf/TOPIC.md`;提案 `spec/open/proposal-io-pipelining.md`。
> 另见 topic `l4-cache-mgmt` / [[BEH-024]](L4 主动驱逐/保留,独立探索)。

当 `PIPE_L4=1` 且 Buffered 模式时,pipe_ring_ buffer 满后仍可通过 `readahead()` 旁路
填充 L4 (page cache),为后续 query 预热。O_DIRECT 模式下此开关无效。

> rationale: L4 (page cache) 容量 = cgroup_limit - RSS,是跨 query 的抽象缓存层。
> Buffered 模式下 pipe_ring_ 读取自然填充 L4;pipe_ring_ 满时仍可 readahead() 旁路预热。
> L4 的价值在于跨 query 局部性,非单 query 收益。

## L4 Page Cache 主动管理 {#BEH-024}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9 source=deduced topic=l4-cache-mgmt -->
<!-- ndf: refines=BEH-006 depends-on=DEC-067,CON-SLA-014,DEC-068 model=MODEL-WILLNEED-001 -->

> **track: promoted** - 提案 `spec/open/proposal-promote-l4.md`（2026-08-03）。
> 装订器: `poc/l4-cache-mgmt/ndf/TOPIC.md`。
> 另见 [[BEH-023]]（`PIPE_L4` 旁路**填充**，deprecated 2026-08-04, DEC-071）。
> WILLNEED 语义核: [[MODEL-WILLNEED-001]]（`spec/models/willneed-readahead.md`）。

Fine rerank 候选循环 MUST 先查 flat_vec_cache (`getFlatVector()`)，
命中则跳过 pread，避免不必要的磁盘 I/O。

`FINE_PREAD=1` 时 MUST 走 pread 路径（不管 `FINE_DIRECT` 是否开启），
保证多线程安全。O_DIRECT + pread 的 buffer MUST 使用 `posix_memalign` 对齐。

当 `L4_WILLNEED=1` 且 Buffered 模式时，Fine rerank 的 WILLNEED readahead
行为 MUST 符合语义核 [[MODEL-WILLNEED-001]]（`pages_needed` 确定后、读提交前对每页
`posix_fadvise(..., WILLNEED)`；默认关闭）。

> rationale: POC 发现 fine rerank 未查 flat_vec_cache，热向量走 pread 读磁盘。
> 在 page cache 不足场景下（256MB cgroup），增大 flat_vec_cache 到 64MB 可提升 QPS 7.5x。
> O_DIRECT 4T 因跳过 pread 走 io_uring 导致 recall 崩到 12%，修复后恢复 95.75%。
> 详见 [[DEC-068]] / `poc/l4-cache-mgmt/ndf/TOPIC.md`。
> WILLNEED 证据与决策见 [[DEC-070]]；可执行预言机见 [[MODEL-WILLNEED-001]]（非 patch/poc 搬迁）。

## 邻接表访问策略 {#BEH-008}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-001 -->

`getInMemNeighbors()` (`disk_hnsw.h:333`) MUST 分三条路径:

1. **CSR 内存邻接表**(`has_inmem_adjacency_ == true`):
   - 非压缩:直接返回 `&adj_csr_neighbors_[adj_csr_offsets_[new_id]]`
   - 压缩:解码 `adj_csr_compact_` 从 `adj_csr_byte_offsets_[new_id]` 到 `csr_decode_buf_` (thread_local)
2. **BlockCache fallback**: `CachedBlock::getNeighbors()`

## WILLNEED 后台线程化 {#BEH-027}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.5 source=observed topic=multi-thread-scaling -->
<!-- ndf: refines=BEH-024 depends-on=DEC-070,DEC-074,CON-SLA-014 model=MODEL-WILLNEED-001 -->

> **track: promoted** - 提案 `spec/open/proposal-promote-mt-scaling.md`（2026-08-05）。
> 装订器: `poc/multi-thread-scaling/ndf/TOPIC.md`。

当 `WILLNEED_BG=1` 时，`posix_fadvise(WILLNEED)` MUST 由后台 I/O 线程统一提交，
搜索线程通过无锁 SPSC slot 传递 page 列表。

后台线程 MUST 轮询所有 slot 的 `ready` flag（`memory_order_acquire`），
对 ready slot 中的 pages 批量调用 `posix_fadvise`，完成后清除 flag。

搜索线程 MUST NOT 在 `WILLNEED_BG=1` 时直接调用 `posix_fadvise`（避免内核锁竞争）。

当 `VL_POOL_THREADS=N` 且 `NUM_THREADS >= N` 时，searchKnn MUST 复用
thread_local VisitedList（`reset()` 递增 curV），而非每次创建新实例。
`NUM_THREADS < N` 时 MUST 走原始创建路径（避免低并发 thread_local 开销）。

> rationale: 12T+ 时 posix_fadvise 内核锁竞争占 6.27%，VisitedList memset 占 10.29%。
> A2 无锁后台线程消除锁竞争，16T +72.8% QPS。C2 自适应池化消除 cache bouncing。
> 详见 [[DEC-074]] / `poc/multi-thread-scaling/ndf/TOPIC.md`。
> source: poc/multi-thread-scaling/ndf/evidence/a2-lockless-bg-20260805.md ; comprehensive-sweep-20260805.md

## WILLNEED BG 页合并 {#BEH-028}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.6 source=observed topic=l4-cache-mgmt -->
<!-- ndf: refines=BEH-027 depends-on=DEC-070,DEC-074,DEC-075,CON-SLA-014 -->

> **track: promoted (partial)** - 提案 `spec/open/proposal-promote-l4-d2.md`（2026-08-06）。
> 装订器: `poc/l4-cache-mgmt/ndf/TOPIC.md`。

当 `WILLNEED_BG=1` 且 `PAGE_MERGE_BG=1` 时，后台线程 MUST 对每个 slot 中的 pages
排序后合并连续页为单次 `posix_fadvise` 调用，减少 syscall 数量。

**适用场景**: 仅 256MB cgroup 高并发 (12T+)。512MB 下有害 (readahead 窗口过大挤占热页)。
**不推荐默认开启**。用户 MUST 仅在 256MB cgroup 场景下设置 `PAGE_MERGE_BG=1`。

> rationale: 256MB page cache 极度紧张时 syscall 开销占比大，合并减少 ~60% fadvise 调用。
> 512MB page cache 充裕时排序开销 > syscall 节省收益。
> source: poc/l4-cache-mgmt/ndf/evidence/d2-bg-page-merge-20260805.md

## PQ 距离间隙自适应 EF {#BEH-033}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.8 source=observed topic=helmsman-adaptive -->
<!-- ndf: refines=BEH-004 depends-on=API-017 -->

> **track: promoted** - 提案 `spec/open/proposal-promote-helmsman-adaptive.md`（2026-08-06）。
> 装订器: `poc/helmsman-adaptive/ndf/TOPIC.md`。
> Promotes: helmsman-adaptive (层次 A); 层次 B rejected (DEC-081)。

当 `ADAPTIVE_EF=1` 时，搜索 MUST 在 Phase A（PQ 粗筛）结束后计算 gap_ratio =
dist[k] / dist[k-1]，并据此动态调整 Phase B 候选数：

- gap_ratio ≥ ADAPTIVE_EASY_GAP → Phase B 限制候选数为 ADAPTIVE_EASY_EF
- gap_ratio ≤ ADAPTIVE_HARD_GAP → Phase B 限制候选数为 ADAPTIVE_HARD_EF
- 否则 → Phase B 限制候选数为 REFINE_EF（标准行为）

**默认关闭**（`ADAPTIVE_EF` 默认 0）。opt-in。

**适用场景**（[[DEC-084]] sustained 实测修正）：**256MB 与 512MB cgroup 均有收益**，
高并发（≥ 4T）收益更明显。sustained 口径实测（N=1000, R=15）：

| cgroup | 线程 | vs BASE（聚合 QPS） | Recall |
|--------|------|-------------------|--------|
| 256MB | 4T | **+28.3%** | 95.81% |
| 256MB | 16T | **+31.4%** | 95.81% |
| 512MB | 4T | **+12.5%** | 95.80% |
| 512MB | 16T | **+26.4%** | 95.80% |

> ⚠️ **已修正的历史误判**：本条款原写“512MB cgroup 下收益不明显或略有退化”。
> 该判断源于 cache-warmed 测量（warmup 后 512MB 确实无 I/O 压力，所以看不到收益）。
> 诚实测量（[[CON-SLA-019]] 禁预热）下 512MB 依然 I/O bound，+12.5~26.4%。

**recall 约束**: 启用时 recall MUST ≥ 95%（sustained 实测 95.80–95.81%）。

> rationale: SIFT1M 的 PQ gap 分布极窄 (P50=1.006)，大多数 query 无明显距离拐点，
> 但减少候选数直接减少 page cache 压力 → 提升 QPS。
> 层次 B (Fine Rerank 早终止) 在 pread 批量读取架构下无效 (DEC-081)。
> 本机制基于**运行时在线信号**（PQ gap_ratio）而非离线训练模型，
> 因此对 query 分布漂移鲁棒 —— 与 [[BEH-034]] 的对照见 [[DEC-084]] §6。
> source: poc/helmsman-adaptive/ndf/TOPIC.md ; poc/sustained-query-benchmark/ndf/evidence/r3-r5-sweep-20260806.md

## GBDT 学习式候选数预测 {#BEH-034}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.11 source=observed topic=gbdt-retrain -->
<!-- ndf: refines=BEH-004 depends-on=API-018,DEC-084 -->

> **track: promoted** - 提案 `spec/open/proposal-promote-gbdt-learned-pruning.md`（2026-08-06）。
> 装订器: `poc/gbdt-learned-pruning/ndf/TOPIC.md`。
> Promotes: gbdt-learned-pruning。
>
> ⚠️ **收益已证伪，条款降级 must → may**（[[DEC-084]] §5，2026-08-06）。
> 机制与代码正确且保留；**当前模型的收益在 sustained 场景下不成立**。

当 `LEARNED_EF=1` 时，搜索 MUST 在 Phase A 结束后提取 11 维 PQ 距离特征向量，
通过 GBDT 模型（100 棵 LightGBM 决策树, 编译期嵌入 C++ if-else 规则表）预测
Phase B 最优候选数，并乘以 `GBDT_MARGIN` 系数后截断候选列表。

**特征**: n_coarse, d0, d9, dk, dk1, gap_ratio, d_mean, d_std, d_cv, d_ratio_01, d_ratio_09

**模型**: SIFT1M 官方 10K query 池训练，100 棵树, max_depth=4, 182KB C++ 规则表。
推理延迟 <0.1μs，无运行时 Python 依赖。

**默认关闭**（LEARNED_EF 默认 0）。opt-in。
与 ADAPTIVE_EF (BEH-033) 互斥；若两者同时开启，LEARNED_EF 优先。

**recall 约束**: 启用时 recall MUST ≥ 95%（sustained 实测 95.87%，满足）。

### 收益状态：重训练后有效 ✅

| 测量口径 | GBDT 增益 | 有效性 |
|---------|----------|--------|
| 200q + query 预热 | +3.3~6.0% | ❌ cache-warmed |
| base-sampled 10Kq (原模型) | +33~124% | ❌ GT self-match 污染 |
| 官方池 sustained (原模型) | −0.9~+1.8% | ❌ 训练数据污染 |
| **官方池 sustained (GBDT-v2)** | **+12.3~47.4%** | ✅ |

**GBDT-v2 vs ADAPTIVE_EF (sustained, 聚合 QPS)**:

| 配置 | GBDT vs ADAPT |
|------|---------------|
| 512MB 1T | +0.7% |
| 512MB 4T | -1.2% |
| 512MB 16T | +11.4% |
| 256MB 1T | +3.6% |
| 256MB 4T | +8.4% |
| 256MB 16T | +8.4% |

GBDT-v2 在高并发 (16T) 下显著优于 ADAPTIVE，多特征建模在高 I/O 争用下信息量更高。

**复活根因**: 原模型训练数据来自 base-sampled 10K query（self-match 污染），
标签 P50=21 系统性偏低。用官方 10K query 池重训后，标签 P50=26（+24%），
模型预测 avg_n=60.3（vs 原 ~30），更保守但有效。

**margin 推荐**: 0.8（默认）。0.7 为激进选项；0.9 为保守选项。

> rationale: GBDT 多特征建模利用 11 维 PQ 距离分布预测 per-query 候选数，
> 在 I/O bound 场景下减少不必要的 Fine Rerank I/O。与 [[BEH-033]]（ADAPTIVE_EF）
> 互为补充：ADAPTIVE 使用单一 gap_ratio 信号（在线自适应），GBDT 使用多特征
> 离线模型（更精准但依赖训练数据质量）。高并发下 GBDT 优势显著。
> 训练数据质量是关键：self-match 污染不仅影响 recall 指标，还污染训练标签
> （[[MODEL-SUSTAINED-001]] 不变量 I4 推论）。参见 [[DEC-084]] §5 复活记录。
> source: poc/gbdt-retrain/ndf/evidence/r4-sustained-three-way-20260807.md
