# 提案：promote sustained-param-retuning（Sustained 口径调参）

> track: promote
> Topic: sustained-param-retuning
> 装订器: `poc/sustained-param-retuning/ndf/TOPIC.md`
> 基线 Trunk: `8784cc8`; POC 完成 commit: `8784cc8`
> 提出日期: 2026-08-07
>
> Status: Proposed
> Promotes: sustained-param-retuning

## 1. 动机

[[DEC-084]] 确立 sustained 为权威口径。但所有主线参数最优值（除 GBDT_MARGIN）均来自
200q cache-warmed 口径，sustained 下从未验证。

POC `poc/sustained-param-retuning/` 完成 R0-R4 全扫描，发现：
- 256MB cgroup 有显著调参空间（agg QPS +6-10%, steady QPS +7-14%）
- 512MB cgroup 参数基本不变
- VL_POOL_THREADS / CACHE_MB 在 sustained 下无显著优化空间

## 2. 语义核决策

**不要**蒸馏 L3 语义核。理由：本 POC 仅修改推荐参数值（API 注释 + DEC），不改代码、
不改行为语义。L1 条款 + VER 足够。

## 3. 变更内容

### 3.1 不改代码

本 promote **不修改 Trunk `src/`**。代码中的默认值（REFINE_EF=200, FLAT_VEC_MB=64 等）
不变。变更仅在 spec 层面的"测量常用"推荐值和文档。

### 3.2 条款修改

| 条款 | 修改 |
|------|------|
| [[API-011]] | FLAT_VEC_MB "测量常用"追加 sustained 推荐；REFINE_EF 追加 sustained 256MB 推荐 90 |
| [[API-017]] | ADAPTIVE_EASY_EF 追加 sustained 256MB 推荐 40；更新适用场景注释 |
| [[DEC-084]] | 追加 §12 sustained 调参结论 |
| 新增 [[DEC-086]] | Sustained 口径调参决策 |

### 3.3 SLA 影响

本次仅修改推荐参数，不改 SLA 数值。SLA 仍基于 EF=100 + ADAPTIVE easy_ef=50 测量。
使用新参数（EF=90 + easy_ef=40）可达更高 QPS，但 recall 余量更薄（95.10% vs 95.80%）。

## 4. 证据

### R0: REFINE_EF 扫描

| EF | recall | 256MB 16T agg QPS | vs EF=100 |
|----|--------|------------------|-----------|
| 80 | 95.02% ✅ | 2,602 | +28.9% |
| 90 | 95.56% ✅ | 2,293 | +13.6% |
| 100 | 96.00% | 2,018 | baseline |

### R1: ADAPTIVE 重校准

| Config | recall | 256MB 16T agg QPS |
|--------|--------|------------------|
| EF=90, eef=50 | 95.37% ✅ | 2,967 |
| EF=90, eef=40 | 95.10% ✅ | 3,131 |
| EF=90, eef=40, eg=1.004 | 94.93% ❌ | 3,359 |

### R3: 最优组合验证

| 配置 | recall | 256MB 16T agg | 256MB 16T steady |
|------|--------|--------------|-----------------|
| OLD (EF=100, FVC=64, eef=50) | 95.54% | 2,892 | 3,615 |
| ALT (EF=90, FVC=64, eef=40) | 95.10% | **3,176 (+9.8%)** | **4,111 (+13.7%)** |

### R4: VL_POOL + CACHE_MB

±2-5% 噪声范围，无显著优化空间。当前默认合理。

## 5. 晋升条件核对

| 条件 | 状态 |
|------|------|
| sustained 下 recall ≥ 95% | ✅ 95.10% (256MB 最优组合) |
| 新参数 QPS > 旧参数 + 5% | ✅ +9.8% agg, +13.7% steady (256MB 16T) |
| 同 seed 可复现 | ✅ (R0/R1/R3 多轮一致) |
| 无 graphcheck 新增 error | ⏳ 验证中 |

## 6. 执行步骤

1. 修改 [[API-011]]: 追加 sustained 推荐值注释
2. 修改 [[API-017]]: 追加 sustained easy_ef=40 注释
3. 新增 [[DEC-086]]: Sustained 调参决策
4. TOPIC -> promoted, COMMITS 记录
5. ndf_index + graphcheck
6. 更新 optimization-roadmap P2.10 标记完成
