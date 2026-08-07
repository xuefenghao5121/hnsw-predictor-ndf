# 提案：Sustained 口径下主线调参优化空间重新评估

> track: poc
> 提出日期：2026-08-07
> 基线 Trunk：`85ec98c`
>
> Status: Implemented on 2026-08-07 (promoted)

## 1. 调研洞察

### 1.1 核心问题

当前所有主线参数的最优值均在 **200q cache-warmed** 口径下确定。
[[DEC-084]] 已证实该口径高估 QPS 1.73-7.60×，且 I/O 行为与 sustained 场景根本不同。

200q 下"最优"的参数，在 sustained 下可能并非最优：
- 200q working set ~10MB 全进 page cache -> I/O ≈ 0 -> 调的是**内存搜索性能**
- sustained working set 持续变化 -> 真实 I/O bound -> 调的是**I/O 效率**

两种场景的瓶颈分布不同，最优参数点必然不同。

### 1.2 参数确定依据审计

| 参数 | 当前最优值 | 确定依据 | 口径 | Sustained 下是否重测？ |
|------|----------|---------|------|---------------------|
| `REFINE_EF` | 100 | [[DEC-072]] SIFT1M 200q | cache-warmed | ❌ 未重测 |
| `FLAT_VEC_MB` (512MB) | 160 | [[DEC-073]] 200q 4T | cache-warmed | ❌ 未重测 |
| `FLAT_VEC_MB` (256MB) | 64 | [[DEC-073]] 200q 4T | cache-warmed | ❌ 未重测 |
| `ADAPTIVE_EASY_EF` | 50 | [[DEC-080]] 200q profiling | cache-warmed | ❌ 未重测 |
| `ADAPTIVE_EASY_GAP` | 1.006 | [[DEC-080]] 200q profiling | cache-warmed | ❌ 未重测 |
| `ADAPTIVE_HARD_GAP` | 1.002 | [[DEC-080]] 200q profiling | cache-warmed | ❌ 未重测 |
| `ADAPTIVE_HARD_EF` | 200 | [[DEC-080]] 200q profiling | cache-warmed | ❌ 未重测 |
| `GBDT_MARGIN` | 0.8 | R5 sustained 调优 | **sustained** | ✅ 已调优 |
| `VL_POOL_THREADS` | 14 | [[DEC-074]] 200q 12T | cache-warmed | ❌ 未重测 |
| `CACHE_MB` | 64 | 200q 实践 | cache-warmed | ❌ 未重测 |
| `PAGE_MERGE_BG` | 1(256MB) / 0(512MB) | [[DEC-075]] 200q 16T | cache-warmed | ❌ 未重测 |

**结论：除 GBDT_MARGIN 外，所有参数的最优值均来自 cache-warmed 口径，sustained 下未验证。**

### 1.3 Sustained 下的 recall 余量

| 模式 | recall | 余量（vs 95% 门槛） |
|------|--------|------------------|
| BASE (EF=100) | 96.00% | **1.00pp** |
| ADAPTIVE | 95.80% | 0.80pp |
| GBDT-v2 (margin=0.8) | 95.87% | 0.87pp |

BASE 有 1.0pp 余量 -> 可以尝试更激进的参数（降 EF、降 FVC），用 recall 换 QPS。
200q 下 recall=95.75%，余量仅 0.75pp，很多激进参数被否决。
sustained 下 recall=96.00%，余量更大，**之前被否的参数可能可行**。

### 1.4 关键发现：200q 否决的参数在 sustained 下可能可行

| 参数 | 200q 结论 | Sustained 下预期 |
|------|---------|----------------|
| `ADAPTIVE_EASY_EF=40` | ❌ recall=94.95% (< 95%) | ✅ 可能可行（sustained recall 更高） |
| `ADAPTIVE_EASY_EF=30` | ❌ 未测（预期更差） | ⚠️ 可能刚好达标 |
| `REFINE_EF=80` | ❌ 未测（200q 下 EF=100 最优） | ✅ I/O bound 下减 EF = 减 I/O = +QPS |
| `FLAT_VEC_MB=200` (512MB) | ❌ 200q 下 160 最优 | ✅ sustained working set 更大，可能需要更多缓存 |

### 1.5 Sustained 下瓶颈分布变化

200q (cache-warmed): I/O ≈ 0, 瓶颈 = PQ 计算 + VisitedList
sustained: I/O = 主瓶颈, PQ 计算 + VisitedList 占比下降

**含义**：
- 减少 I/O 的参数（降 EF、更激进 ADAPTIVE/GBDT 裁剪）在 sustained 下收益更大
- 增加内存缓存的参数（升 FVC）在 sustained 下可能收益不同（page cache 预算竞争）

## 2. 调参空间（按优先级）

### P1: REFINE_EF 扫描（最高优先）

当前 EF=100（[[DEC-072]] 基于 200q 确定）。sustained 下 I/O 是瓶颈，减 EF 直接减 Phase B 候选数 = 减 I/O。

扫描范围：{60, 70, 80, 90, 100, 120}
- recall 约束：≥ 95%
- 预期：EF=80 可能是 sustained 最优（recall ~95.5%, QPS +10-15%）

### P2: ADAPTIVE_EF 阈值重校准

当前 easy_ef=50（[[DEC-080]] 基于 200q，easy_ef=40 被否因 recall < 95%）。
sustained 下 recall 基线更高，easy_ef=40 可能可行。

扫描范围：
- easy_ef: {30, 40, 50, 60}
- easy_gap: {1.004, 1.006, 1.008}
- 保持 hard_ef=200, hard_gap=1.002

### P3: FLAT_VEC_MB 重扫描

当前 512MB->160, 256MB->64（[[DEC-073]] 基于 200q）。
sustained 下 working set 更大，FVC 命中率可能不同。

扫描范围：
- 512MB: {64, 100, 160, 200, 240}
- 256MB: {32, 48, 64, 96}

### P4: GBDT_MARGIN 已调优（仅记录）

R5 已在 sustained 下扫描 {0.7, 0.8, 0.9, 1.0, 1.1}，推荐 0.8。

### P5: VL_POOL_THREADS 重验证

当前 14（[[DEC-074]] 基于 200q 12T）。sustained 下多线程 I/O 行为不同。

扫描范围：{8, 10, 12, 14, 16, 999(关闭)}

### P6: CACHE_MB 重验证

当前 64。sustained 下 BlockCache 与 page cache 的角色不同（200q 下 BlockCache 是唯一缓存，sustained 下 page cache 也参与）。

扫描范围：{32, 48, 64, 96, 128}

## 3. 实验计划概要

### R0: REFINE_EF 扫描（P1）

512MB + 256MB × 1T/4T/16T × EF={60,70,80,90,100,120}
- 固定 BASE 模式（不开 ADAPTIVE/GBDT）
- 找 sustained 下 EF 的 recall-QPS Pareto 前沿

### R1: ADAPTIVE 阈值重校准（P2）

在 R0 确定的新 EF 基线上，扫描 ADAPTIVE 参数
- easy_ef: {30, 40, 50}
- easy_gap: {1.004, 1.006, 1.008}

### R2: FLAT_VEC_MB 重扫描（P3）

在 R0+R1 确定的参数基线上，扫描 FVC
- 512MB: {64, 100, 160, 200, 240}
- 256MB: {32, 48, 64, 96}

### R3: 最优组合验证

R0-R2 确定的最优参数组合，跑完整 sustained 矩阵
- 对比：旧参数 BASE vs 新参数 BASE vs 新参数 ADAPTIVE vs 新参数 GBDT

### R4: VL_POOL + CACHE_MB（如时间允许）

低优先级，仅在 R0-R3 有余力时执行。

## 4. 晋升条件

- 新参数组合在 sustained 下 recall ≥ 95%
- 新参数组合 QPS > 旧参数 QPS（sustained，至少一个配置 +5%）
- 若新参数 != Trunk 默认值 -> 修改默认值并 promote
- 若新参数 = 旧参数 -> 确认旧参数在 sustained 下仍最优，记录为验证结果

## 5. 表面冲突检查

无活跃 exploring 主题（csr-on-disk 刚 rejected）。
`explore_surface: search-adaptive,refine-ef,cache-tuning` 与已 promoted 主题不冲突。

## 6. 不做的事

- 不改 Trunk `src/`（POC 阶段）
- 不改 DEEP10M 参数（先 SIFT1M 验证）
- 不引入新机制（只调现有参数）
- 不改测量方法论（用 sustained benchmark，N=1000, R=15, seed=42）
