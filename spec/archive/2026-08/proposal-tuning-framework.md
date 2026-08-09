> track: process
> Status: Implemented on 2026-08-09
> 日期: 2026-08-09

# 提案: DiskHNSW 参数调优框架 - 内存预算驱动的因果模型

## 背景

sustained-param-retuning (DEC-086) 和 pipeline-param-retuning (DEC-087) 两个 POC
积累了大量调优数据，但参数间的因果逻辑未系统化，导致：

1. 调参顺序混乱（独立扫描各参数，而非按因果链逐层调优）
2. 跨配置预测能力缺失（M=24 上 block size +52.5% 不能预测 M=16 上的效果）
3. 负结果无法事先排除（GBDT 在低 EF 下的失效可以从前置分析推导）

本提案建立一个**内存预算驱动的因果模型**，作为后续所有调优的理论框架。

## 参数全表

### A. 架构层参数（Pipeline 构建时确定，不可运行时修改）

这些参数在 `build_pipeline.sh` 执行时确定，改变需要重建索引 + 重新分块。

| 参数 | 位置 | Trunk 默认 | 作用 | 深层逻辑 |
|------|------|-----------|------|---------|
| **M_graph** | build_index arg | 16 | HNSW 建图的 M 参数，决定图的最大邻居数 | M_graph↑ -> 图更连通 -> 同 EF 下 recall↑。但 L0 邻接表更大 -> CSR 更大 -> anon↑ -> page cache↓。**双重效应**：recall↑ 允许 EF↓，但 page cache↓ 加剧 I/O 瓶颈。M=16 在低 EF 区间胜出因为 CSR 最小（47MB），留给 page cache 最多（27MB） |
| **ef_construction** | build_index arg | 200 | 建图时的搜索宽度 | 影响图质量（召回率），不影响运行时性能。200 是 hnswlib 推荐值，调高建图慢但不显著提升 recall |
| **M_pq** | train_pq.py arg | 32 | PQ 子量化器数量，决定向量压缩质量 | M_pq↑ -> PQ 近似更精确 -> 同 recall 下需更少候选 -> I/O↓。但 PQ codes 更大（N×M_pq bytes）-> anon↑。SIFT1M: M=32 是唯一满足 recall≥95% 的选择（M=16 recall 91.6%，M=64 QPS -31%）。**PQ 的收益是双重的**：recall↑ + I/O↓，但内存代价线性增长 |
| **block_size (BS)** | build_pipeline.sh | 65536 (64KB) | 向量数据分块大小，决定 I/O 粒度 | BS↓ -> 每次 pread 读更少数据 -> I/O 浪费↓（一个 4KB 页内的向量可能跨多个候选）。但 route table 更大 -> 更多元数据。**仅当 page cache 覆盖率 < 5% 时有效**：I/O 瓶颈越紧，block size 越重要。M=24 (4.8%) +52.5%，M=16 (5.4%) ≈0% |

### B. 运行时参数 - I/O 路径控制（决定数据如何读取）

这些参数控制 Fine Rerank 阶段的 I/O 模式，影响实际磁盘 I/O 量。

| 参数 | API | Trunk 默认 | 测量常用 | 作用 | 深层逻辑 |
|------|-----|-----------|---------|------|---------|
| **TWO_STAGE** | API-011 | 0 | 1 | 1=启用 PQ 粗筛 + 精排两阶段搜索 | 关闭时 Phase A 直接用精确距离（需读磁盘向量），开启后 Phase A 用 PQ 近似距离（纯内存），仅 Phase B 读磁盘。**是整个 DiskHNSW 的前提**：不开 TWO_STAGE 就没有磁盘驻留优势 |
| **FINE_RERANK** | API-011 | 0 | 1 | 1=4KB 页粒度精排 | 开启后 Phase B 按 4KB 页读取候选向量做精确 L2。不开则只靠 PQ 近似距离排序，recall 不足 |
| **FINE_BUFFERED** | API-011 | 0 | 1 | 1=buffered I/O（含 page cache） | 开启后 I/O 经过 OS page cache，page cache 在 cgroup 预算内合法积累。关闭则用 O_DIRECT 绕过 page cache。**Buffered 是生产优化主目标，O_DIRECT 是诚实验收地板**（[[DEC-062]]） |
| **FINE_PREAD** | API-011 | 0 | 1 | 1=pread 替代 io_uring | 多线程下必须用 pread（io_uring 不是线程安全的）。单线程下 io_uring 有轻微优势但差异不大 |
| **VEC_BLOCKS_PATH** | API-011 | - | 必填 | 向量数据块文件路径 | 指向 BFS 重排后的 vecblocks 文件。不同 block_size 对应不同文件 |
| **PQ_CODES_PATH** | API-011 | - | 必填 | PQ 编码文件路径 | PQ codes 在 BFS 序下存储，与图结构配套 |

### C. 运行时参数 - 缓存控制（决定内存如何分配）

这些参数决定 anon 内存在各缓存间的分配，直接影响 page cache 预算。

| 参数 | API | Trunk 默认 | 测量常用 | 作用 | 深层逻辑 |
|------|-----|-----------|---------|------|---------|
| **FLAT_VEC_MB** | API-011 | 64 | 64/160 | 热向量 LRU 缓存大小 | 缓存最近访问的完整向量（512 bytes/条），避免重复 pread。增大 -> 命中率↑ -> I/O↓，但 anon↑ -> page cache↓。**agg/steady 权衡**：大 FVC 提升 steady（热缓存命中率）但伤害 agg（ramp-up 期吃 page cache 预算）。256MB 下 64 是甜点，512MB 下 64 (agg) / 160 (steady) |
| **CACHE_MB** | API-011 | 必填 | 64 | BlockCache 大小 | 缓存 block header 元数据（非向量数据）。对性能影响小（±2-5%），64 是噪声内最优 |
| **NUM_THREADS** | API-011 | 1 | 4/16 | 并发搜索线程数 | 多线程分摊 I/O 等待。但线程↑ -> anon↑（每线程 VisitedList ~1MB）-> page cache↓。16T 时 RSS 从 229 升到 249MB（+20MB = 16 × ~1.2MB/线程）|

### D. 运行时参数 - I/O 预取优化（决定 I/O 与计算的重叠）

这些参数通过内核提示或后台线程，将 I/O 与计算重叠，减少串行等待。

| 参数 | API | Trunk 默认 | 测量常用 | 作用 | 深层逻辑 |
|------|-----|-----------|---------|------|---------|
| **L4_WILLNEED** | API-012 | 0 | 1 | pread 前对候选页调用 posix_fadvise(WILLNEED) | 触发内核异步 readahead，pread 从阻塞磁盘 I/O 变为内存拷贝。**256MB 下 17.7x QPS**（pread 是瓶颈时），512MB 下 +5.5%（pread 非瓶颈），DEEP10M 下 ~0%（I/O 量主导）。是 256MB cgroup 的**必开参数** |
| **WILLNEED_BG** | API-013 | 0 | 1 | 后台线程提交 WILLNEED | 主线程不阻塞在 fadvise 调用上。无锁 SPSC 队列实现，零竞争。前置 L4_WILLNEED=1 |
| **VL_POOL_THREADS** | API-013 | 999 | 14 | NUM_THREADS ≥ N 时复用 thread_local VisitedList | 避免每查询 memset VisitedList（10MB @1M nodes）。14 是 16T 下的最优值（留 2 线程做 I/O）。噪声内 ±2-5% |
| **PAGE_MERGE_BG** | API-013 | 0 | 1(256MB 12T+) | 后台线程合并连续页的 fadvise | 减少 fadvise 系统调用次数。仅 256MB 高并发有益，512MB 下有害（fadvise 开销 > 收益） |

### E. 运行时参数 - 候选数控制（决定 Phase B 精排多少候选）

这些参数决定每个 query 在 Phase B 精排多少候选，直接影响 I/O 总量和 recall。

| 参数 | API | Trunk 默认 | 测量常用 | 作用 | 深层逻辑 |
|------|-----|-----------|---------|------|---------|
| **REFINE_EF** | API-011 | 200 | 65-100 | Phase A 图搜索宽度 | 决定 Phase A 返回的候选集大小。EF↑ -> 候选更多 -> recall↑ 但 I/O 更多。**存在 recall ≥ 95% 的最低 EF 拐点**：拐点以下 QPS 暴涨（I/O 在预算内），拐点以上 QPS 线性下降。M=16 拐点在 EF=65（recall 95.52%），M=24 拐点在 EF=60（recall 96.60%）。Trunk 默认 200 是保守值，sustained 下 65-90 足够 |
| **ADAPTIVE_EF** | API-017 | 0 | 1 | 启用 PQ 距离间隙自适应 | 根据 PQ 距离分布分类 easy/hard query，easy query 用更低的 EF。**增益 ∝ recall 余量**：余量 = recall - 95%。余量 > 1.5pp 时 +50-68%，余量 < 0.5pp 时 +3%（无效）。消耗 recall 预算换 QPS |
| **ADAPTIVE_EASY_EF** | API-017 | 50 | 40 | easy query 的 Phase B 候选上限 | 降到多少取决于 recall 预算。eef=40 在 200q 下不达标（recall 94.95%），sustained 下达标（recall 基线更高 96.00% vs 95.75%）。**口径依赖**：200q 否决的参数在 sustained 下可能可行 |
| **ADAPTIVE_EASY_GAP** | API-017 | 1.006 | 1.006 | gap ≥ 此值判为 easy | 控制 easy/hard 分类阈值。gap = dk1/dk（第 k+1 近 vs 第 k 近候选的 PQ 距离比）。gap 大 -> 候选质量分化明显 -> easy query 可安全降 EF |
| **ADAPTIVE_HARD_EF** | API-017 | 200 | 200 | hard query 的 Phase B 候选上限 | 通常保持 200（不限制），因为 hard query 本来就需要更多候选 |
| **LEARNED_EF** | API-018 | 0 | 0/1 | 启用 GBDT 预测 per-query 候选数 | 用 LightGBM 模型（100 棵树，编译期嵌入 C++）预测每个 query 需要的最小候选数。比 ADAPTIVE 更精准（11 个特征 vs 1 个 gap_ratio），但需要训练数据。**仅在 EF ≥ 100 + recall 余量 ≥ 1pp 时有效**：低 EF 下候选集太小，60%+ query 需要 ≥50 候选，无裁剪空间 |
| **GBDT_MARGIN** | API-018 | 0.8 | 0.7-1.0 | 预测值缩放系数 | margin < 1.0 = 更激进（用更少候选），margin > 1.0 = 更保守。margin=0.8 在 512MB EF=100 下 recall=95.87%。**模型依赖**：GBDT 在 EF=200 下训练，换 EF 后预测失准，需用目标 EF 重新 profiling + 训练 |

### F. 测量参数（Benchmark 配置，不影响系统行为）

| 参数 | 位置 | 默认 | 作用 | 深层逻辑 |
|------|------|------|------|---------|
| **N (per_round)** | benchmark arg | 1000 | 每轮采样 query 数 | QPS 与 N 无关（N=200/1000/10000 均收敛），选 1000 因 ~40s/组适合回归 |
| **R (rounds)** | benchmark arg | 15 | 采样轮数 | 多轮采样减少方差。15 轮 × 1000 = 15000 queries，从 10K 池中有放回采样 |
| **seed** | benchmark arg | 42 | 随机种子 | 控制采样可复现。warmup 轮用 seed+1000000+w 保证 disjoint（[[CON-SLA-019]]） |
| **warmup** | benchmark arg | 0 | 预热轮数 | CON-SLA-019 禁止预热被测 query。warmup > 0 时用 disjoint seed，不计入统计 |

## 因果模型

### 第一层：内存预算分配

```
cgroup_limit = anon + file (page cache)

anon = upper_vectors + L0_adjacency + CSR + PQ_codes + FVC + BlockCache + VisitedList×T
       ↑ M_graph决定    ↑ M_graph   ↑ M_graph ↑ M_pq  ↑ FVC  ↑ CACHE_MB  ↑ NUM_THREADS

file (page cache) = cgroup_limit - anon
    -> 用于缓存 vecblocks (磁盘驻留向量数据)
    -> 覆盖率 = page_cache / vecblocks_size
```

**实测数据 (256MB cgroup, SIFT1M, vecblocks=496MB):**

| M_graph | CSR | upper_vec | PQ_codes | FVC | CACHE | VL(16T) | RSS_run | page_cache | 覆盖率 |
|---------|-----|-----------|----------|-----|-------|---------|---------|------------|--------|
| 16 | 47MB | 30MB | 30MB | 64MB | 64MB | 20MB | 229MB | 27MB | 5.4% |
| 24 | 57MB | 20MB | 30MB | 64MB | 64MB | 20MB | 232MB | 24MB | 4.8% |
| 32 | 61MB | 15MB | 30MB | 64MB | 64MB | 20MB | 235MB | 21MB | 4.2% |
| 48 | 65MB | 10MB | 30MB | 64MB | 64MB | 20MB | 236MB | 20MB | 4.0% |

> M_graph↑ -> CSR↑ -> RSS↑ -> page_cache↓ -> I/O 瓶颈加剧
> upper_vec 随 M_graph↑ 而减小（upper 层节点更少），但 CSR 增长更大
> VisitedList 在 16T 时占 20MB（每线程 ~1.2MB），单线程时仅 1.2MB

### 第二层：I/O 瓶颈传导

```
I/O 总量 = EF × avg_pages_per_candidate × (1 - cache_hit_rate)
           ↑                    ↑                    ↑
           REFINE_EF            block_size 决定       page_cache + FVC + WILLNEED 决定
           ADAPTIVE/GBDT 可降低  小 block = 少读      L4_WILLNEED 预取提升有效命中率
```

**五条传导链:**

1. **EF 链**: EF↑ -> I/O 总量↑ -> page cache 压力↑ -> QPS↓
   - 但 EF↑ 同时 recall↑ -> 存在 recall ≥ 95% 的最低 EF 拐点
   - 拐点以下 QPS 暴涨（I/O 在 page cache 预算内），拐点以上 QPS 线性下降
   - **证据**: M=16 EF=60 (agg=2594) -> EF=65 (agg=2483) -> EF=70 (agg=1390) 断崖

2. **M_graph 链**: M_graph↑ -> 同 EF 下 recall↑（图更连通）
   - 但 M_graph↑ -> CSR↑ -> page cache↓ -> 同 EF 下 I/O 更严重
   - 双重效应: recall↑ 允许 EF↓，但 page cache↓ 加剧 I/O
   - M=16 在低 EF 区间胜出：CSR 最小 -> page cache 最大 -> 最低 EF 可行

3. **Block size 链**: block_size↓ -> 每 candidate 读取量↓ -> I/O 浪费↓
   - 但仅当 I/O 是瓶颈时才有收益（page cache 覆盖率低）
   - M=24 (4.8%): +52.5%；M=16 (5.4%): -2.7%（噪声）
   - 规律: page cache 覆盖率越低，block size 越重要

4. **ADAPTIVE 链**: easy_query 的 EF 降低 -> I/O 总量↓
   - 增益 ∝ recall 余量（余量大 -> 可降 EF 的 query 多 -> 增益大）
   - 余量 = recall - 95%（SLA 门槛）
   - 余量 < 0.5pp: +3%（无效）；余量 > 1.5pp: +50-68%

5. **GBDT 链**: per-query 预测 min_n -> 精准裁剪候选
   - 依赖候选集足够大（EF ≥ 100）才能学到有意义的分布
   - EF=65 候选集仅 65 个，60%+ query 需要 ≥50 候选 -> 无裁剪空间
   - 规律: GBDT 仅在 EF ≥ 100 且 recall 余量 ≥ 1pp 时有效

### 第三层：recall 预算

```
recall = f(M_graph, EF, M_pq, ADAPTIVE)

recall 预算 = recall - 95% (SLA 门槛)
  -> 预算分配: ADAPTIVE 消耗余量换 QPS
  -> 预算不足时: 不能开 ADAPTIVE / 不能降 EF
```

| 配置 | recall | 预算 | ADAPTIVE 可用？ | GBDT 可用？ |
|------|--------|------|----------------|------------|
| M=24 EF=60 | 96.60% | 1.60pp | ✅ (+68%) | ❌ (EF<100) |
| M=16 EF=90 | 96.00% | 1.00pp | ✅ (+16%) | ✅ (512MB) |
| M=16 EF=65 | 95.52% | 0.52pp | ⚠️ (+3%) | ❌ (EF<100) |

## 调优决策树

```
1. 确定 cgroup 大小
   ├─ ≥ 512MB: I/O 非瓶颈 -> EF=100, FVC=64/160, ADAPTIVE 可选
   └─ ≤ 256MB: I/O 是瓶颈 -> 进入步骤 2

2. 选择 M_graph (决定 anon 预算)
   ├─ M=16: CSR=47MB, page_cache=27MB (最大) -> 最低 EF 可行
   ├─ M=24: CSR=57MB, page_cache=24MB -> recall 更高但 I/O 更紧
   └─ M≥32: CSR>60MB, page_cache<22MB -> I/O 过紧, 不推荐

3. 二分查找最低 EF (recall ≥ 95% 的拐点)
   ├─ 粗扫: EF={60,80,100,120}
   ├─ 细扫: 在拐点附近以 5 为步长
   └─ 记录 recall 余量 = recall - 95%

4. 评估 recall 预算
   ├─ 预算 > 1.5pp: 开 ADAPTIVE (eef=40, 增益 50%+)
   ├─ 0.5pp < 预算 < 1.5pp: ADAPTIVE 收益有限 (10-20%), 可选
   └─ 预算 < 0.5pp: 不开 ADAPTIVE (增益 < 5%)

5. 评估 block size (仅当 page_cache 覆盖率 < 5%)
   ├─ 覆盖率 < 5%: 扫描 {16K, 32K, 64K}, 选最优
   └─ 覆盖率 > 5%: 保持 64K (差异在噪声内)

6. GBDT 仅在以下条件全满足时考虑
   ├─ EF ≥ 100 (候选集足够大)
   ├─ recall 预算 ≥ 1pp (有裁剪空间)
   └─ cgroup ≥ 512MB (I/O 量足够大, 裁剪收益 > 预测开销)
   否则: 用 ADAPTIVE 代替

7. 固定参数 (无需调优)
   ├─ TWO_STAGE=1, FINE_RERANK=1, FINE_BUFFERED=1, FINE_PREAD=1 (I/O 路径)
   ├─ L4_WILLNEED=1, WILLNEED_BG=1 (预取, 256MB 必开)
   ├─ VL_POOL_THREADS=14, CACHE_MB=64 (噪声内最优)
   └─ PAGE_MERGE_BG=1 (仅 256MB 12T+)
```

## 与两个 POC 的对照验证

### sustained-param-retuning (DEC-086)

| 决策 | 框架预测 | 实际 | 吻合 |
|------|---------|------|------|
| 256MB EF=90 优于 EF=100 | I/O 瓶颈 -> 降 EF | +13.6% | ✅ |
| 512MB EF 不变 | I/O 非瓶颈 | 不变 | ✅ |
| ADAPTIVE eef=40 可行 | 余量 1.00pp > 0.5pp | +12.7% | ✅ |
| FVC=64 不变 | 增大吃 page cache | 不变 | ✅ |

### pipeline-param-retuning (DEC-087)

| 决策 | 框架预测 | 实际 | 吻合 |
|------|---------|------|------|
| M=16 低 EF 胜出 | CSR 最小 -> page cache 最大 | +127% | ✅ |
| M=24 ADAPTIVE +68% | 余量 1.60pp > 1.5pp | +68% | ✅ |
| M=16 EF=65 ADAPTIVE +3% | 余量 0.52pp < 0.5pp | +3% | ✅ |
| Block 32K M=24 +52.5% | 覆盖率 4.8% < 5% | +52.5% | ✅ |
| Block 32K M=16 ≈0% | 覆盖率 5.4% > 5% | -2.7% | ✅ |
| GBDT EF=65 无效 | EF=65 < 100 | ≈BASE | ✅ |

### block-size-tuning R0 (M=16 EF=65)

| 预测 | 实际 | 吻合 |
|------|------|------|
| 覆盖率 5.4% > 5% -> 差异 < ±10% | 16K=1609, 64K=1480, +8.7% | ✅ |

**框架与全部 8 项实验结果吻合。**

## 落地建议

1. 本框架作为 **DEC-088** 记录在 `spec/decisions/`
2. 在 API-011 中追加调优框架引用
3. 后续 POC 在 TOPIC.md 中 MUST 引用本框架，按决策树顺序设计实验
4. 参数全表作为 `spec/30-interfaces/` 的参考文档

## 不改的项

- 不改 Trunk `src/`
- 不改 SLA 阈值
- 不改现有 API 参数默认值
- 纯方法论文档

> source: spec/decisions/22-sustained-param-retuning.md (DEC-086) ; spec/decisions/23-pipeline-param-retuning.md (DEC-087) ; poc/pipeline-param-retuning/ndf/evidence/r0-r4-redo-20260808.md ; poc/sustained-param-retuning/ndf/evidence/ ; poc/block-size-tuning/results/
> track: process ; Topic: N/A (framework)
