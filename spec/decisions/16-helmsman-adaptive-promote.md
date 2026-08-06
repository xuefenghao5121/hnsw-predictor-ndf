# DEC-080: SIFT1M PQ Gap 校准 + Recall/QPS 权衡

> topic: helmsman-adaptive
> status: accepted
> date: 2026-08-06
> Promotes: helmsman-adaptive (层次 A)

## 背景

HELMSMAN (OSDI 2026) 提出 PQ 距离间隙可用于自适应调整 Fine Rerank 候选数。
POC `helmsman-adaptive` 验证此机制在 DiskHNSW 上的有效性。

## 决策

### 1. 阈值校准

SIFT1M PQ gap 分布实测范围 1.000-1.045（P50=1.006），远窄于论文假设的 1.0-1.2+。
基于实测分布校准默认阈值：

| 参数 | 论文建议 | SIFT1M 校准值 | 依据 |
|------|---------|-------------|------|
| easy_gap | 1.15 | 1.006 | ≈P50，约 50% query 判为 easy |
| hard_gap | 1.03 | 1.002 | ≈P25，约 25% query 判为 hard |
| easy_ef | — | 50 | recall ≥ 95% 约束下的最优 |
| hard_ef | — | 200 | 很少触发（SIFT1M 无极难 query） |

### 2. Recall/QPS 权衡

用户约束: recall ≥ 95%（放宽自产品 SLA 的 95.75%）。

| 配置 | recall | QPS 增益 | 决策 |
|------|--------|---------|------|
| easy_ef=70 (conservative) | 95.75% | +11% | 可选保守配置 |
| easy_ef=50 (calibrated) | 95.30% | +31% | **采纳**（满足 ≥95%） |
| easy_ef=40 (aggressive) | 94.95% | — | 拒绝（<95%） |

### 3. 适用场景限定

- **256MB cgroup ≥4T**: 明确推荐（+31% QPS）
- **512MB / 单线程**: 不推荐（page cache 充裕，无收益）
- **默认关闭**: opt-in 机制保护现有行为

### 4. 不新增 SLA

ADAPTIVE_EF 的 QPS 增益为 opt-in 可选行为，不写入 stable CON-SLA must。

## 证据

- R0 profiling: SIFT1M gap 分布 (P10=1.001, P50=1.006, P90=1.022, Max=1.045)
- R2 scaling: 256MB 1T/4T/8T/16T 全量对比
- R3 回归: 512MB 持平/略退
- POC: `poc/helmsman-adaptive/ndf/TOPIC.md`
