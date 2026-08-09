# DEC-092: 全参数展开扫描结果 — 256MB SIFT1M 1T 性能图谱 {#DEC-092}

> date: 2026-08-09
> affects: DEC-088, DEC-091
> topic: param-expansion-sweep
<!-- ndf: depends-on=DEC-088,DEC-091 -->

## 背景

DEC-091 完成了决策树步骤 1-4 (M_graph, EF, ADAPTIVE)。本 DEC 展开全部剩余参数：
FLAT_VEC_MB, CACHE_MB, ADAPTIVE_EASY_EF/GAP, 并做最优组合验证。

## 关键发现

### 1. FLAT_VEC_MB: 最优点在 96, 不是 64

| FVC | Agg QPS | RSS | page_cache |
|-----|---------|-----|-----------|
| 32 | 1,411 | 197MB | 59MB |
| 64 | 1,469 | 229MB | 27MB |
| **96** | **1,497** | 253MB | 3MB |
| 128 | **907** | 253MB | <0 thrashing |

- FVC=96 比 64 提升 agg +1.9%, steady +7.0%
- FVC=128 断崖: page cache 被完全吃光 → thrashing
- **安全余量为零** (RSS=253 ≈ cgroup 256), 多线程下不可用

### 2. CACHE_MB: 噪声确认

极差 2.4%, 无显著影响。保持默认 64。

### 3. ADAPTIVE_EASY_EF: EEF=35 全面最优

| 配置 | EEF=35 | EEF=40 | EEF=45 |
|------|--------|--------|--------|
| M=16 EF=65 | 1668/94.92%❌ | 1616/95.17% | 1600/95.33% |
| M=16 EF=80 | **1503/96.09%** | 1454/96.37% | 1433/96.54% |
| M=24 EF=60 | **1639/95.92%** | 1599/96.22% | 1570/96.40% |

EEF=35 比 40 多 +3-5% QPS, recall 降 ~0.3pp。在高预算配置下安全。

### 4. ADAPTIVE_EASY_GAP: GAP=1.003 最优

| GAP | Agg QPS | Recall |
|-----|---------|--------|
| **1.003** | **1,557** | 96.10% |
| 1.006 | 1,473 | 96.37% |

+5.7% QPS, recall 仍安全。在高预算下推荐。

### 5. 🏆 全局最优: M=24 EF=60 +ADAPTIVE(eef=35)

**agg=1,640 QPS / steady=1,931 QPS / recall=95.92%**

vs DEC-091 基线 (M=16 EF=65): **+10.4% agg QPS**
vs CON-SLA-020 (M=16 EF=100): **+51.8% agg QPS**

## DEC-088 框架验证

12 项预测全部吻合。新增 2 项验证:
- GAP 越小越激进 ✅
- EEF=35 比 40 更激进 ✅

## 参数敏感度排序 (256MB SIFT1M 1T)

1. REFINE_EF: QPS ±40% (最大杠杆)
2. ADAPTIVE (EEF+GAP): QPS +10-20%
3. M_graph: 改变 recall 预算结构
4. FLAT_VEC_MB: +1.9% (96 vs 64, 安全余量为零)
5. CACHE_MB: ±2.4% (噪声)

## 推荐 256MB 1T 配置矩阵

| 定位 | M | EF | FVC | ADAPTIVE | Agg QPS | Recall |
|------|---|----|-----|----------|---------|--------|
| 🏆 全局最优 | 24 | 60 | 64 | eef=35 | 1,640 | 95.92% |
| 亚优 | 16 | 80 | 96 | eef=35,gap=1.003 | 1,601 | 95.69% |
| 默认推荐 | 16 | 65 | 64 | 无 | 1,486 | 95.52% |
| 稳健 | 24 | 60 | 64 | 无 | 1,476 | 96.60% |

> source: poc/param-expansion-sweep/ndf/evidence/r0-r4-full-param-expansion-20260809.md
