# DEC-091: 框架决策树系统性重扫结果 + DEC-087 数据修正 {#DEC-091}

> date: 2026-08-09
> affects: DEC-087, DEC-088
> topic: framework-driven-optimization
<!-- ndf: depends-on=DEC-088 -->

## 背景

DEC-087 记录的 "M=16 EF=65 = 2,483 QPS" 经查为 cgroup 泄漏 (pgmajfault=0, file_bytes=0)。
本 DEC 记录严格 cgroup 下的系统性重扫结果, 并修正 DEC-087。

## cgroup 有效性验证

独立验证运行 (fdo_v3 cgroup, 256MB):
- pgmajfault = 7,701 ✅
- pgfault = 134,001 ✅
- workingset_refault_file = 104,198 ✅
- memory.peak = 268,435,456 (= 256MB, 触顶) ✅
- memory.current = 268,333,056 (99.97% 利用率) ✅

## SIFT1M 1T 256MB 完整扫描 (17 组)

### Pareto 前沿 (recall ≥ 95%)

| Config | Agg QPS | Recall | 定位 |
|--------|---------|--------|------|
| M=16 EF=65 +ADAPTIVE | **1,637** | 95.17% | ⚡ 激进最优 |
| M=16 EF=65 | **1,486** | 95.52% | ⭐ 默认推荐 |
| M=24 EF=60 | **1,476** | 96.60% | 🛡️ 稳健最优 |

### M=16 EF 全扫描 (无断崖, 平滑过渡)

| EF | Agg QPS | Recall |
|----|---------|--------|
| 50 | 1,759 | 93.33% |
| 55 | 1,650 | 94.19% |
| 60 | 1,555 | 94.94% |
| **65** | **1,486** | **95.52%** |
| 70 | 1,408 | 96.00% |
| 75 | 1,315 | 96.45% |
| 80 | 1,254 | 96.79% |
| 90 | 1,166 | 97.38% |
| 100 | 1,081 | 97.76% |

### ADAPTIVE 增益

| Base EF | Agg QPS | +ADAPTIVE | ΔQPS | Recall Δ |
|---------|---------|-----------|------|----------|
| 65 | 1,486 | 1,637 | +10.2% | -0.35pp |
| 80 | 1,254 | 1,473 | +17.4% | -0.42pp |
| 90 | 1,166 | 1,386 | +18.8% | -0.47pp |

## DEC-087 数据修正

| 指标 | DEC-087 记录 | 修正值 | 说明 |
|------|-------------|--------|------|
| M=16 EF=65 agg QPS | 2,483 | **1,486** | cgroup 泄漏修正 |
| M=16 EF=65 steady QPS | 3,289 | **1,640** | cgroup 泄漏修正 |
| "EF=65→70 QPS 断崖" | -44% | **-5.3%** | 断崖不存在 |
| "vs EF=100 +127%" | 错误 | **+37.5%** | 真实增益 |

## 结论

1. **DEC-088 框架决策树有效**: 预测方向正确 (M=16 低 EF 最优), 具体数字修正
2. **推荐配置**: M=16 EF=65 (默认) / M=24 EF=60 (稳健) / M=16 EF=65 +ADAPTIVE (激进)
3. **ADAPTIVE 价值确认**: recall 余量充足时可提升 QPS 10-19%
4. **DEC-087 数据修正**: QPS 数据全面下调, 但 Pareto 前沿不变

> source: poc/framework-driven-optimization/ndf/evidence/r0-r3-decision-tree-sweep-20260809.md
