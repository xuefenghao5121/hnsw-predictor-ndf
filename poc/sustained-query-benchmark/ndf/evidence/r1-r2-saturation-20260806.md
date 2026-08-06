# R1+R2: 多轮 benchmark 实现与 cache 饱和曲线

> 日期: 2026-08-06
> Topic: sustained-query-benchmark
> Baseline Trunk: `4a33f38`
> 隔离协议: [[CON-SLA-014]] via [[API-016]] (`cgroup_utils.sh`)

## R1: 实现与等价性验证

### 实现要点

`poc/sustained-query-benchmark/benchmark_sustained.cpp`

关键设计：**取消 query warmup**。原 `benchmark_diskhnsw` 在计时前会把全部
待测 query 跑一遍（"Search warmup: run all queries once to warm cache"），
这正是 [[DEC-083]] 所述 cache-warmed 假象的制造机制。本 harness 只保留
CPU 频率 spin，不预热被测 query。

链接 **未修改的 Trunk `src/`** —— 本 POC 只改测量方法论，不改搜索引擎，
因此无 patched copy（符合 [[BEH-018]] 第 6 条）。

### 等价性验证

R=1, N=200, 使用现有 `sift1m_query200.fvecs` + `sift1m_gt200.bin`：

| 指标 | 现有 200q baseline | 本 harness (R=1) |
|------|-------------------|-----------------|
| Recall@10 | 95.75% | **95.75%** ✅ |
| QPS | 3,241 | **250.9** |

**recall 精确一致** → harness 的检索与 recall 计算逻辑正确。

**QPS 相差 12.9×** → 这不是 bug，而是本 POC 要暴露的核心事实：
原 baseline 的 3,241 QPS 完全来自 warmup 把 200q 的 working set (~10MB)
全部装入 page cache。取消 warmup 后，冷启动真实 QPS 仅 250.9。

## R2: cache 饱和曲线 (512MB cgroup, 1T, N=200)

官方 10K query 池随机采样，seed=42，每组独立 `drop_caches`：

| R | Round-1 QPS | 末轮 QPS | 聚合 QPS | 聚合 Recall | 累积 unique |
|---|------------|---------|---------|------------|-----------|
| 1 | 244.7 | — | 244.7 | 95.35% | 200 |
| 5 | 245.6 | 1,393.2 | 688.0 | 96.42% | 965 |
| 10 | 237.0 | 1,451.0 | 909.2 | 96.50% | 1,837 |
| 20 | 244.7 | 1,622.3 | 1,141.0 | 96.25% | 3,314 |
| 50 | 241.8 | **1,671.1** | 1,348.5 | **96.06%** | 6,346 |

### 关键发现 1：曲线方向与预期相反 —— 是 ramp-up，不是 decay

提案预期 "QPS 随轮数下降并趋于平稳"。实测**相反**：QPS 从 ~245 单调**上升**
到 ~1,670，约在 R=20 饱和。

根因：`drop_caches` 后 Round 1 是**完全冷启动**。随后被预热的是
**query-无关的共享状态**：

| 共享状态 | 大小 | 特性 |
|---------|------|------|
| 图 CSR (compact + offsets) | 47MB | 所有 query 共用 |
| PQ codes | 30MB | 所有 query 共用 |
| flat-vec cache (FVC=160) | 160MB | 热点向量，跨 query 复用 |
| Phase B 向量页 | 随 query 变化 | 唯一 query-相关部分 |

前三项合计 ~237MB，在 512MB 预算内可长期驻留。所以随机换 query
**不能**驱逐它们 —— 反而是轮数越多，它们越充分预热。

这修正了一个此前的误判：`working set ~10MB / ~488MB` 这种算法只统计了
Phase B 向量页，忽略了占主导的 query-无关共享状态。

### 关键发现 2：recall 96.06% > 95% ✅

这是本 POC 的核心价值。对比三种方案：

| 方案 | QPS 诚实性 | Recall | 可用于 SLA |
|------|-----------|--------|-----------|
| 200q + warmup（现状） | ❌ 高估 12.9× | 95.75% | ❌ QPS 不可信 |
| base-sampled 10Kq（已拒） | ✅ | ❌ 89.71% | ❌ recall 不达标 |
| **官方池多轮采样（本 POC）** | ✅ | ✅ **96.06%** | ✅ |

首次同时满足两个条件。

### 关键发现 3：饱和后 QPS ≈ 1,620–1,671

R=20 与 R=50 的末轮 QPS 分别为 1,622 / 1,671（差 3%，在噪声内），
可判定 **R≥20 达到稳态**。

稳态 QPS ~1,650 与此前 base-sampled 10Kq 测得的 1,428 同量级
（后者偏低是因为 10Kq 单轮无共享状态预热机会）。

## R1/R2 验收

| 检查项 | 结果 |
|--------|------|
| 编译（链接未修改 Trunk src） | ✅ 仅 Trunk 预存 warning |
| R=1 recall 与现有 baseline 一致 | ✅ 95.75% 精确匹配 |
| 饱和曲线可复现（同 seed） | ✅ Round-1 QPS 237–246，±2% |
| 饱和拐点明确 | ✅ R≈20 |
| recall ≥ 95% | ✅ 96.06% @ R=50 |

**R1/R2 通过**。

## 对提案的修正

提案 §4 R2 的预期表述（"QPS 随轮数下降"）**已被证伪**。正确模型：

> 冷启动后 QPS 单调上升至稳态。随机换 query 无法驱逐 query-无关共享状态
> （图 CSR + PQ codes + FVC ≈ 237MB），因此 sustained 稳态高于单轮冷启动。
>
> 真正的 cache-warmed 假象来自 **warmup 预热被测 query 本身**，
> 而非 working set 规模。取消 warmup 是关键，多轮采样保证 query 多样性。

## 命令

```bash
# 等价性验证
./poc/sustained-query-benchmark/benchmark_sustained \
  output/sift1m_graph.bin output/sift1m_bfs.bin \
  output/sift1m_blocks_64k.bin output/sift1m_route_64k.bin \
  data/sift_base.fvecs data/sift1m_query200.fvecs data/sift1m_gt200.bin \
  10 100 --rounds 1 --per-round 200 --seed 42 --verbose

# 饱和曲线
for R in 1 5 10 20 50; do
  TAG=r2 CGROUP_MB=512 THREADS=1 PER_ROUND=200 ROUNDS=$R \
    bash poc/sustained-query-benchmark/run_sustained.sh
done
```

日志：`poc/sustained-query-benchmark/results/r2_512mb_1t_n200_r{1,5,10,20,50}.log`
