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

1. 当前 SLA QPS 数字标注为 "cache-warmed"，保留用于回归验证
2. 新增 10K query 基线作为 "sustained" 场景 SLA
3. CON-SLA-014/016/017 的 QPS 下限保留不变（数字是下限，高估的数字仍满足下限）
4. 后续提案修正 SLA 数字

## 证据

- `poc/gbdt-learned-pruning/ndf/sla-reevaluation.md`
- hnswlib unlimited 10K vs 200q 差距 <1.3x（内存搜索不受 working set 影响）
