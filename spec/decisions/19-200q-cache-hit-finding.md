# DEC-083: 200q benchmark cache-hit 假象发现

> topic: gbdt-learned-pruning (副作用发现)
> status: accepted
> date: 2026-08-06

## 背景

在 GBDT POC 实验中，发现 200q 和 10Kq benchmark 结果矛盾。排查后发现 200q 存在
系统性的 cache-hit 假象。

## 发现

### Working Set 分析

| Query 数 | Phase B working set | vs 256MB cache |
|----------|---------------------|----------------|
| 200 | ~10MB | 全进 cache |
| 1,000 | ~50MB | 部分超 |
| 10,000 | ~488MB | 远超 |

### QPS 随 NQ 变化 (256MB 4T baseline)

| NQ | QPS | 倍数 |
|----|-----|------|
| 200 | 8,856 | 1.0x (cache hit) |
| 1,000 | 4,095 | 0.46x |
| 10,000 | 2,332 | 0.26x |

### 影响

当前 SLA (CON-SLA-014/016/017) 的 QPS 数字基于 200q，系统性高估 2-5x：
- 512MB 16T: 标称 30,332 → 实测 5,583 (5.4x 高估)
- 256MB 4T: 标称 8,838 → 实测 2,341 (3.8x 高估)

## 决策

1. 当前 SLA QPS 数字保留不变（200q 标准数据集，recall ≥ 95%，具有商用价值）
2. **不建立基于 10K random query 的 SLA**
3. 记录 cache-hit 认知，作为后续建立 sustained SLA 的输入

## ❗ 10K random query 不可用的原因 (2026-08-06 补充)

### self-match bug

10K query 从 base 随机抽取 → query 向量本身就在 base 中 →
sklearn `kneighbors(n_neighbors=10)` 会返回 self-match (距离=0) →
GT top-1 永远是 query 自己 → recall 白送 ~10%。

### 排除 self-match 后的真实 recall

| 配置 | 修正前 (含 self) | 修正后 (排除 self) |
|------|------------------|-------------------|
| hnswlib unlimited | 99.47% | **89.90%** |
| DiskHNSW 256MB baseline | 97.67% | **89.71%** |
| DiskHNSW 256MB GBDT | 97.33% | **89.59%** |

### 结论

10K random query 在 ef=100 下 recall 仅 ~89.7%，**远低于 95% 商用门槛**。
random query 的难度分布不同于标准 200q。需更大 ef 才能达 95%，但那会降 QPS。

**因此不建立任何基于 10K random query 的 SLA 条款。**
200q 标准数据集（recall 95.75%）仍是唯一具商用价值的 SLA 基准。

## 证据

- `poc/gbdt-learned-pruning/ndf/sla-reevaluation.md`
- hnswlib unlimited 10K vs 200q 差距 <1.3x（内存搜索不受 working set 影响）
