# 优化路线图 v1.0

> 基准: SIFT1M 2,041 QPS (1T) / 95.70% recall / 273MB RSS
> 日期: 2026-07-30
> 关联: DEC-032, CON-007, ARCH-004

## 目标

在 page cache + disk 两层架构下，消除 cgroup 紧时的 10× QPS 悬崖，
使 150-180MB cgroup 下 QPS 保持在 1,000+。

## 根因确认

```
cgroup reclaim 风暴 = 10× QPS 悬崖
    ↑
process RSS 101MB + page cache working set 24MB = 125MB base
cgroup 180MB - 125MB = 55MB 余量 → 刚好卡在边界
    ↑
需要: process RSS < 70MB + page cache 余量 > 50MB
```

## 优化矩阵

| # | 优化项 | RSS 节省 | QPS 影响 | 复杂度 | 优先级 | 条款 |
|---|--------|---------|---------|--------|--------|------|
| P0 | CSR 图裁剪 (Degree Cap) | -22MB | ±0% | 低 (已有工具) | 🔴 | DEC-033 |
| P1 | Upper Layer PQ 编码 | -28MB | -5% | 中 | 🟡 | DEC-034 |
| P2 | PQ SIMD ADC 加速 | 0 | +20-50% | 中 | 🟢 | DEC-035 |
| P3 | Adaptive REFINE_EF | 0 | +10-20% | 高 | ⚪ | DEC-028 |

## 预期效果

```
Current (273MB RSS): 180MB cgroup → 196 QPS 😱
P0 only (251MB RSS): 180MB cgroup → 800+ QPS ✅
P0+P1 (223MB RSS): 150MB cgroup → 1,000+ QPS ✅
P0+P1+P2: DEEP10M QPS 75 → 200+ ✅
```

## 实施顺序

```
P0 (CSR 裁剪) → 180MB cgroup 验证 → 立即益
    ↓
P1 (Upper PQ) → 150MB cgroup 验证 → 进一步
    ↓
P2 (SIMD PQ)  → DEEP10M 验证 → QPS boost
    ↓
P3 (Adaptive) → profiling → 未来
```
