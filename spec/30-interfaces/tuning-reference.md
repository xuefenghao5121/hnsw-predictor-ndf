# DiskHNSW 参数调优参考 {#DEC-088-REF}

> **参考文档**，非 L1 契约。因果模型与决策树见 [[DEC-088]]。
> track: reference ; depends-on: DEC-088, API-011, API-012, API-013, API-017, API-018

## A. 架构层参数（Pipeline 构建时确定）

| 参数 | 位置 | Trunk 默认 | 作用 | 深层逻辑 |
|------|------|-----------|------|---------|
| **M_graph** | build_index arg | 16 | HNSW 建图的 M 参数 | M↑ -> 图更连通 -> 同 EF 下 recall↑。但 CSR 更大 -> anon↑ -> page cache↓。**双重效应**：recall↑ 允许 EF↓，但 page cache↓ 加剧 I/O。M=16 在低 EF 区间胜出因 CSR 最小（47MB），留给 page cache 最多 |
| **ef_construction** | build_index arg | 200 | 建图搜索宽度 | 影响图质量，不影响运行时性能。200 是 hnswlib 推荐值 |
| **M_pq** | train_pq.py arg | 32 | PQ 子量化器数量 | M_pq↑ -> PQ 更精确 -> 同 recall 需更少候选 -> I/O↓。但 PQ codes 更大 -> anon↑。SIFT1M: M=32 唯一满足 recall≥95% |
| **block_size (BS)** | build_pipeline.sh | 65536 (64KB) | 向量数据分块大小 | BS↓ -> 每次 pread 读更少 -> I/O 浪费↓。但 route table 更大。**仅当 page cache 覆盖率 < 5% 时有效** |

## B. 运行时参数 — I/O 路径控制

| 参数 | API | Trunk 默认 | 测量常用 | 作用 |
|------|-----|-----------|---------|------|
| **TWO_STAGE** | API-011 | 0 | 1 | 1=PQ 粗筛 + 精排两阶段。**DiskHNSW 前提** |
| **FINE_RERANK** | API-011 | 0 | 1 | 1=4KB 页粒度精排 |
| **FINE_BUFFERED** | API-011 | 0 | 1 | 1=buffered I/O（含 page cache） |
| **FINE_PREAD** | API-011 | 0 | 1 | 1=pread 替代 io_uring（多线程必须） |
| **VEC_BLOCKS_PATH** | API-011 | - | 必填 | 向量数据块文件路径 |
| **PQ_CODES_PATH** | API-011 | - | 必填 | PQ 编码文件路径 |

## C. 运行时参数 — 缓存控制

| 参数 | API | Trunk 默认 | 测量常用 | 作用 |
|------|-----|-----------|---------|------|
| **FLAT_VEC_MB** | API-011 | 64 | 64/160 | 热向量 LRU。agg/steady 权衡：大 FVC 提升 steady 但伤害 agg |
| **CACHE_MB** | API-011 | 必填 | 64 | BlockCache 元数据。±2-5% 噪声 |
| **NUM_THREADS** | API-011 | 1 | 4/16 | 并发线程数。线程↑ -> anon↑（每线程 ~1.2MB VisitedList）|

## D. 运行时参数 — I/O 预取优化

| 参数 | API | Trunk 默认 | 测量常用 | 作用 |
|------|-----|-----------|---------|------|
| **L4_WILLNEED** | API-012 | 0 | 1 | pread 前 fadvise(WILLNEED)。**256MB 下 17.7x QPS** |
| **WILLNEED_BG** | API-013 | 0 | 1 | 后台线程提交 WILLNEED。无锁 SPSC 队列 |
| **VL_POOL_THREADS** | API-013 | 999 | 14 | NUM_THREADS ≥ N 时复用 VisitedList |
| **PAGE_MERGE_BG** | API-013 | 0 | 1(256MB 12T+) | 后台合并连续页 fadvise |

## E. 运行时参数 — 候选数控制

| 参数 | API | Trunk 默认 | 测量常用 | 作用 |
|------|-----|-----------|---------|------|
| **REFINE_EF** | API-011 | 200 | 65-100 | Phase A 图搜索宽度。存在 recall ≥ 95% 最低 EF 拐点 |
| **ADAPTIVE_EF** | API-017 | 0 | 1 | PQ 距离间隙自适应。增益 ∝ recall 余量 |
| **ADAPTIVE_EASY_EF** | API-017 | 50 | 40 | easy query 候选上限 |
| **ADAPTIVE_EASY_GAP** | API-017 | 1.006 | 1.006 | easy/hard 分类阈值 |
| **ADAPTIVE_HARD_EF** | API-017 | 200 | 200 | hard query 候选上限（通常不限制） |
| **LEARNED_EF** | API-018 | 0 | 0/1 | GBDT 预测 per-query 候选数。仅 EF ≥ 100 + recall 余量 ≥ 1pp 有效 |
| **GBDT_MARGIN** | API-018 | 0.8 | 0.7-1.0 | 预测值缩放系数 |

## F. 测量参数（Benchmark 配置）

| 参数 | 位置 | 默认 | 作用 |
|------|------|------|------|
| **N (per_round)** | benchmark arg | 1000 | 每轮采样 query 数。QPS 与 N 无关 |
| **R (rounds)** | benchmark arg | 15 | 采样轮数 |
| **seed** | benchmark arg | 42 | 随机种子（warmup 用 seed+1000000+w 保证 disjoint） |
| **warmup** | benchmark arg | 0 | 预热轮数。CON-SLA-019 禁止预热被测 query |

## recall 预算速查

| 配置 | recall | 预算 | ADAPTIVE | GBDT |
|------|--------|------|----------|------|
| M=24 EF=60 | 96.60% | 1.60pp | ✅ (+68%) | ❌ (EF<100) |
| M=16 EF=90 | 96.00% | 1.00pp | ✅ (+16%) | ✅ (512MB) |
| M=16 EF=65 | 95.52% | 0.52pp | ⚠️ (+3%) | ❌ (EF<100) |

> 完整因果模型、决策树、实验对照见 [[DEC-088]]。
