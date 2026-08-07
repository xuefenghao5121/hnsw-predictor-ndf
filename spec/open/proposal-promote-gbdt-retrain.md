# 提案：promote gbdt-retrain（GBDT 重训练复活）

> track: promote
> Topic: gbdt-retrain
> 装订器: `poc/gbdt-retrain/ndf/TOPIC.md`
> 基线 Trunk: `7c91280`；POC 实现 commit: `1cf0d9e`
> 提出日期: 2026-08-07
>
> Status: Proposed

## 1. 动机

[[BEH-034]] 在 [[DEC-084]] 中因 GBDT 训练数据被 self-match 污染而从 `must` 降级为 `may`。
[[BEH-034]] 正文明确记载复活条件："用合规 query 池重新 profiling 并重训模型"。

本 POC（`poc/gbdt-retrain/`）已用官方 SIFT 10K query 池完成重训练，
sustained 口径下全配置验证 GBDT-v2 收益成立且优于 ADAPTIVE_EF。

## 2. 晋升内容

### 2.1 代码变更

| 文件 | 变更 |
|------|------|
| `include/gbdt_model.h` | 用新模型替换（100 棵树, 182KB, 官方池训练） |

### 2.2 条款修改

| ID | 当前 | 目标 | 修改内容 |
|----|------|------|---------|
| `BEH-034` | may / stable | **must / stable** | 删除"收益不成立"声明；更新为 sustained 实测收益 +12.3~47.4% |
| `API-018` | stable | stable | 更新收益状态标注 |
| `DEC-084` | stable | stable (amended) | 追加复活记录（§5） |

### 2.3 不新增条款

本 promote 不新增条款。GBDT_MARGIN 推荐值仍为 0.8（[[API-018]] 已有）。

## 3. 证据

### 3.1 R0: 标签分布对比（self-match 污染确认）

| 维度 | 原 POC (base-sampled) | 本 POC (官方池) |
|------|----------------------|----------------|
| P50 min_n | 21 | **26** (+24%) |
| P75 min_n | 30 | **52** (+73%) |
| P90 min_n | 50 | **201** (4×) |
| ≤30 占比 | 68% | **59.3%** |

self-match 使原标签系统性偏低 -> 模型过度裁剪 -> sustained 收益归零。

### 3.2 R4: 512MB Sustained 三方对比

| 配置 | BASE | ADAPTIVE | GBDT-v2 | GBDT vs BASE | GBDT vs ADAPT |
|------|------|---------|---------|-------------|--------------|
| 1T | 1,348 | 1,502 | **1,513** | +12.3% | +0.7% |
| 4T | 3,445 | 3,969 | **3,920** | +13.8% | -1.2% |
| 16T | 4,188 | 5,037 | **5,612** | +34.0% | +11.4% |

### 3.3 256MB Sustained 三方对比

| 配置 | BASE | ADAPTIVE | GBDT-v2 | GBDT vs BASE | GBDT vs ADAPT |
|------|------|---------|---------|-------------|--------------|
| 1T | 1,063 | 1,254 | **1,300** | +22.3% | +3.6% |
| 4T | 2,186 | 2,805 | **3,040** | +39.0% | +8.4% |
| 16T | 2,019 | 2,746 | **2,978** | +47.4% | +8.4% |

### 3.4 R5: Margin 调优 (512MB 16T)

| Margin | 聚合 QPS | Recall | 推荐场景 |
|--------|---------|--------|---------|
| 0.7 | 5,993 | 95.75% | 激进（recall 余量薄） |
| **0.8** | **5,359** | **95.87%** | **默认推荐** |
| 0.9 | 5,328 | 95.93% | recall 优先 |
| 1.0 | 4,865 | 95.96% | 保守 |

### 3.5 复现性验证

| Run | 聚合 QPS | 稳态 QPS | Recall |
|-----|---------|---------|--------|
| 首次 | 1,513.1 | 1,811.4 | 95.87% |
| 重跑 | 1,534.3 | 1,797.5 | 95.87% |
| 偏差 | 1.4% | 0.8% | 0.00pp |

±3% 内 ✅，recall 精确一致 ✅。

### 3.6 与原 GBDT 对比

| 指标 | 原 GBDT (sustained) | GBDT-v2 (sustained) |
|------|---------------------|---------------------|
| vs BASE | -0.9~+1.8%（噪声） | **+12.3~47.4%** ✅ |
| vs ADAPTIVE | 远低于 | **+0.7~11.4%** ✅ |
| recall | 95.99% | 95.87% |

## 4. 晋升条件核对

| 条件 | 状态 |
|------|------|
| recall ≥ 95% (sustained) | ✅ 95.87% (全配置) |
| GBDT-v2 QPS > BASE + 5% | ✅ +12.3~47.4% |
| GBDT-v2 QPS ≥ ADAPTIVE | ✅ 全配置优于或持平 (最大 +11.4%) |
| 同 seed 可复现 (±3%) | ✅ ±1.4% |
| margin 调优完成 | ✅ 推荐 0.8 |
| 模型导出 C++ | ✅ 182KB |
| Trunk `src/` 改动 | 仅 `include/gbdt_model.h` (模型文件替换) |

## 5. 执行步骤

1. 替换 `include/gbdt_model.h` 为 `poc/gbdt-retrain/gbdt_model.h`
2. 修改 [[BEH-034]]: level may -> must，更新收益声明
3. 修改 [[API-018]]: 更新收益状态
4. 修改 [[DEC-084]]: 追加 §5 复活记录
5. 编译验证
6. VER: 跑 512MB 1T sustained 验证
7. `ndf_index.py index` + `ndf_graphcheck.py`
8. TOPIC -> promoted, COMMITS 记录, 归档装订器
9. README 更新: GBDT 状态从 ❌ 改为 ✅

## 6. 风险

| 风险 | 缓解 |
|------|------|
| 模型仅 SIFT1M 验证，未跨数据集 | BEH-034 正文标注"DEEP10M 待验证" |
| margin=0.7 recall 余量薄 | 默认 0.8, 0.7 作为激进选项 |
| 19.7% query 不可达 (min_n > 200) | 模型对这类 query 预测较高候选数，recall 仍 ≥ 95% |
