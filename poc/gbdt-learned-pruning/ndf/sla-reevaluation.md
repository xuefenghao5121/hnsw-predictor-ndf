# SLA 数据重新评估 + GBDT 价值重估

> Created: 2026-08-06
> Related: [[CON-SLA-014]], [[CON-SLA-016]], [[CON-SLA-017]], [[BEH-033]], gbdt-learned-pruning

## 1. 发现：200 query benchmark 的 cache-hit 假象

### Working Set 分析

| Query 数量 | Phase B 总候选 | Working Set | vs 256MB cache | vs 512MB cache |
|-----------|---------------|-------------|----------------|----------------|
| 200 | 20K | ~10MB | 全进 cache ✅ | 全进 cache ✅ |
| 1,000 | 100K | ~50MB | 部分超 | 基本容纳 |
| 10,000 | 1M | ~488MB | 远超 ❌ | 远超 ❌ |

### QPS vs NQ 趋势 (256MB 4T baseline)

| NQ | QPS | Recall |
|----|-----|--------|
| 200 | 8,856 | 95.80% |
| 1,000 | 4,095 | 87.70% |
| 10,000 | 2,332 | 97.67% |

**QPS 下降 3.8x** (200→10K)。200q 测的是 cache-hit 后的内存搜索性能。

### 当前 SLA 高估倍数

| SLA 条款 | 200q 数字 | 10K 数字 | 高估倍数 |
|----------|----------|---------|---------|
| CON-SLA-014 (512MB 1T) | 3,241 | 1,428 | 2.27x |
| CON-SLA-014 (512MB 4T) | 9,090 | 4,129 | 2.20x |
| CON-SLA-014 (512MB 16T) | 30,332 | 5,583 | 5.43x |
| CON-SLA-016 (256MB 4T) | 8,838 | 2,341 | 3.78x |

## 2. GBDT 价值重估

### 三方对比随 NQ 变化 (256MB 4T)

| NQ | Baseline | Adaptive | GBDT | GBDT vs Base | Adaptive vs Base |
|----|----------|----------|------|-------------|-----------------|
| 200 | 8,856 | 9,349 | 9,127 | +3.1% | +5.6% |
| 1,000 | 4,095 | 5,555 | 7,032 | +71.7% | +35.7% |
| 10,000 | 2,332 | 3,204 | 4,418 | +89.4% | +37.4% |

**结论: GBDT 的真实价值在 I/O bound 场景（≥1K query）下极大。**
200q 下表现平淡是因为 I/O 不是瓶颈。

### GBDT 10K query 全量 scaling

256MB cgroup:

| 线程 | Baseline | GBDT | Δ |
|------|---------|------|---|
| 1T | 1,121 | 1,555 | +38.7% |
| 4T | 2,341 | 4,418 | +88.7% |
| 8T | 2,314 | 4,919 | +112.6% |
| 16T | 2,099 | 4,707 | +124.3% |

512MB cgroup:

| 线程 | Baseline | GBDT | Δ |
|------|---------|------|---|
| 1T | 1,428 | 1,903 | +33.2% |
| 4T | 4,129 | 6,324 | +53.2% |
| 8T | 5,199 | 9,433 | +81.4% |
| 16T | 5,583 | 11,149 | +99.7% |

## 3. 建议行动

### ⚠️ 10K random query 不可用作 SLA (2026-08-06 修正)

**self-match bug**: 10K query 从 base 随机抽取 → query 向量在 base 中 →
sklearn `kneighbors(n_neighbors=10)` 包含 self-match (距离=0) → GT top-1 永远是 self
→ recall 白送 ~10%。

排除 self-match 后的真实 recall:

| 配置 | 修正前 | 修正后 |
|------|--------|--------|
| hnswlib 10Kq | 99.47% | **89.90%** |
| DiskHNSW 256MB baseline | 97.67% | **89.71%** |
| DiskHNSW 256MB GBDT | 97.33% | **89.59%** |

**结论**: 10K random query 在 ef=100 下 recall 仅 ~89.7%，远低于 95% 商用门槛。
random query 难度分布不同于标准 200q。**不建立基于 10K random query 的 SLA**。

GBDT 的 QPS 相对增益 (+39~114%) 不受影响，但绝对数字不可作为商用依据。

### 待做

建立 sustained SLA 需要**标准 SIFT query set 的大规模子集**（如重复 1000-5000 次
标准 query，或使用完整 10K 标准 query set），确保 recall ≥ 95%。

### GBDT promote 决策 (已完成)

- BEH-034 + API-018 已 promoted (opt-in, LEARNED_EF 默认 0)
- 200q 标准数据集下 recall 95.75% ✅
- I/O bound 场景下 QPS 相对增益显著

### 200q SLA 的用途

200q 仍是唯一满足 recall ≥ 95% 的 SLA 基准:
- 算法正确性 (recall@10 ≥ 95%)
- cache-warm 场景性能上限
- 快速回归验证
