# DEC-088: DiskHNSW 参数调优框架 — 内存预算驱动因果模型 {#DEC-088}

> date: 2026-08-09
> affects: API-011, API-017, API-018, DEC-086, DEC-087
> topic: N/A (framework, cross-topic reference)

## Context

sustained-param-retuning (DEC-086) 和 pipeline-param-retuning (DEC-087) 两个 POC
积累了大量调优数据，但参数间的因果逻辑未系统化，导致：

1. 调参顺序混乱（独立扫描各参数，而非按因果链逐层调优）
2. 跨配置预测能力缺失（M=24 上 block size +52.5% 不能预测 M=16 上的效果）
3. 负结果无法事先排除（GBDT 在低 EF 下的失效可以从前置分析推导）

本决策建立一个**内存预算驱动的因果模型**，作为后续所有调优的理论框架。

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
   - 但仅当 I/O 是瓶颈时才收益（page cache 覆盖率低）
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

## 与实验数据的对照验证

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

## 后续约束

1. 后续调优 POC 在 `TOPIC.md` 中 MUST 引用本框架（`depends-on=DEC-088`）
2. 实验设计 MUST 按决策树顺序（cgroup → M_graph → EF → ADAPTIVE → block size → GBDT）
3. 参数全表参考文档见 `spec/30-interfaces/tuning-reference.md`

## 不改的项

- 不改 Trunk `src/`
- 不改 SLA 阈值
- 不改现有 API 参数默认值
- 纯方法论文档

> source: spec/decisions/22-sustained-param-retuning.md (DEC-086) ; spec/decisions/23-pipeline-param-retuning.md (DEC-087) ; poc/pipeline-param-retuning/ndf/evidence/r0-r4-redo-20260808.md ; poc/sustained-param-retuning/ndf/evidence/ ; poc/block-size-tuning/results/
