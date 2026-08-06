# 提案：sustained-query-benchmark — 多轮随机采样持续查询基准

> track: poc
>
> explore_surface: test-infra,benchmark-methodology
>
> 提出日期：2026-08-06
> 基线 Trunk：`4a33f38`
>
> Status: Implemented on 2026-08-06

## 1. 背景与动机

### 1.1 已证实的两个测量缺陷

**缺陷 A：200q cache-warmed 假象（[[DEC-083]]）**

现有 SLA 全部基于 200 query 标准子集。实测发现其 Phase B working set 仅 ~10MB，
在 warmup 阶段全部进入 page cache，实测阶段 I/O ≈ 0：

| SLA 条款 | 200q 标称 QPS | 10K 实测 QPS | 高估倍数 |
|----------|--------------|-------------|---------|
| CON-SLA-014 (512MB 1T) | 3,241 | 1,428 | 2.27× |
| CON-SLA-014 (512MB 16T) | 30,332 | 5,583 | 5.43× |
| CON-SLA-016 (256MB 4T) | 8,838 | 2,341 | 3.78× |

结论：200q 测的是"内存搜索性能"，不是 DiskHNSW 的设计目标（磁盘驻留向量）。

**缺陷 B：base-sampled query 的 self-match 污染**

为破除缺陷 A，曾从 `sift_base.fvecs` 随机抽取 10K 向量作为 query。该方案有致命缺陷：
query 向量本身在 base 中 → brute-force GT 的 top-1 永远是 self（距离 0）→ recall 白送 ~10%。

排除 self-match 后真实 recall：

| 系统 | 含 self | 排除 self |
|------|---------|----------|
| hnswlib unlimited | 99.47% | **89.90%** |
| DiskHNSW 256MB baseline | 97.67% | **89.71%** |
| DiskHNSW 256MB + GBDT | 97.33% | **89.59%** |

排除后 recall < 95% 商用门槛 → base-sampled query 分布难度不同于标准 query set，
不可用于 SLA。已据此撤除 `CON-SLA-019` / `CON-SLA-020`（commit `4a33f38`）。

### 1.2 需求

建立一个**同时满足**以下条件的基准方法：

1. **破除 cache warmup 假象** — working set 必须持续变化，反映真实 I/O bound 场景
2. **recall 可信且 ≥ 95%** — 必须使用真实 query 分布 + 官方 groundtruth
3. **可复现** — 随机采样必须 seed 可控

## 2. 方案设计

### 2.1 核心思路：标准 query 池 + 多轮随机采样

使用 **完整标准 SIFT query set（10,000 queries + 官方 groundtruth）** 作为采样池，
每轮从池中随机采样 N 个 query 执行，共 R 轮。

```
query pool: 标准 sift_query.fvecs (10,000 × 128) + sift_groundtruth.ivecs (10,000 × 100)
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
     Round 1         Round 2    ...  Round R
   sample N=200    sample N=200      sample N=200
   (seed=base+1)   (seed=base+2)     (seed=base+R)
        │               │               │
        └───────────────┴───────────────┘
                        ▼
        aggregate: total QPS + overall recall@k
```

### 2.2 为什么这个方案有效

| 目标 | 机制 |
|------|------|
| 破除 cache 假象 | 每轮 query 集合不同 → 累积 working set 随轮数增长 → page cache 无法容纳全部 |
| recall 可信 | 标准 SIFT query set 是官方设计的查询分布（不在 base 中，无 self-match） |
| 官方 GT | 使用 `sift_groundtruth.ivecs`，无需自行 brute-force 计算 |
| 可复现 | `--seed` 参数控制采样，同 seed 产生同序列 |
| 规模可调 | N ∈ {200, 1000, 10000}，R 可调 → 覆盖从 cache-hot 到完全 I/O bound 的连续谱 |

### 2.3 与被拒方案的对比

| 方案 | working set 变化 | recall 可信 | 结论 |
|------|-----------------|------------|------|
| 单次 200q（现状） | ❌ 固定 10MB | ✅ 官方 GT | cache-warmed 假象 |
| base-sampled 10Kq | ✅ 488MB | ❌ self-match 污染 | 已拒（recall 89%） |
| **标准池多轮采样** | ✅ 随轮数增长 | ✅ 官方 GT | **本提案** |

## 3. 拟新增条款（draft）

### 多轮随机采样持续查询基准 {#BEH-035}
<!-- ndf: kind=req level=tbd layer=L1 status=draft since=0.9.10 source=proposed -->
<!-- ndf: topic=sustained-query-benchmark -->

benchmark 工具 SHOULD 支持多轮随机采样模式：从标准 query 池中每轮随机采样
N 个 query，共执行 R 轮，聚合报告总体 QPS 与 recall@k。

- 采样 MUST 使用标准 query set（非 base-sampled），保证无 self-match 污染
- 采样 MUST 由 seed 控制，保证可复现
- recall 计算 MUST 基于官方 groundtruth
- 报告 SHOULD 同时给出每轮 QPS（观察 cache 饱和过程）与总体聚合值

> rationale: 单次固定 query 集会被 page cache 完全吸收（DEC-083）。
> 多轮随机采样使累积 working set 持续增长，逼近真实生产场景。

### 多轮采样 benchmark CLI {#API-019}
<!-- ndf: kind=interface level=tbd layer=L1 status=draft since=0.9.10 source=proposed -->
<!-- ndf: topic=sustained-query-benchmark depends-on=BEH-035 -->

`benchmark_sustained` 参数：

| 参数 | 说明 |
|------|------|
| `--rounds R` | 轮数 |
| `--per-round N` | 每轮采样 query 数 |
| `--seed S` | 随机种子（默认 42） |
| `--pool <query.fvecs>` | 标准 query 池 |
| `--gt <groundtruth.ivecs>` | 官方 groundtruth |

## 4. 实验计划

### R0：数据准备与验证
- 下载标准 SIFT 完整数据集（`sift.tar.gz`, 168MB, FTP irisa.fr）
- 提取 `sift_query.fvecs` (10,000 × 128) + `sift_groundtruth.ivecs` (10,000 × 100)
- 验证：前 200 个 query 与现有 `sift1m_query200.fvecs` 一致（确认现有 200q 是标准子集）
- 验证：官方 GT 与现有 `sift1m_gt200.bin` 一致
- **验收**：一致性确认，无 self-match

### R1：多轮 benchmark 实现
- 在 `poc/sustained-query-benchmark/` 实现 `benchmark_sustained.cpp`
- 基于现有 `benchmark_diskhnsw.cpp`，增加多轮采样循环
- 报告：每轮 QPS + 每轮 recall + 聚合 QPS + 聚合 recall
- **验收**：R=1, N=200, seed=42 时结果与现有 200q benchmark 一致（±2% 噪声）

### R2：cache 饱和曲线（N=200，R 扫描）
- 固定 N=200，R ∈ {1, 5, 10, 20, 50}
- 观察 QPS 随轮数的衰减曲线 → 找到 cache 饱和点
- **预期**：R=1 高 QPS（cache-warmed），R↑ 后 QPS 下降并趋于平稳（sustained）
- **验收**：曲线呈现明确的饱和拐点

### R3：规模扫描（N ∈ {200, 1000, 10000}）
- 各 N 下测 sustained QPS（R 取 R2 确定的饱和轮数）
- 对比 recall 是否保持 ≥ 95%
- **验收**：recall ≥ 95%（若不达标，说明 ef=100 需调整，记录为发现）

### R4：cgroup 扫描（256MB / 512MB）
- 在两种 cgroup 预算下重复 R3
- 严格遵循 [[CON-SLA-014]] 隔离协议（drop_caches + memory.max）
- **验收**：完整 sustained 性能矩阵

### R5：优化开关有效性复测
- 在 sustained 场景下复测 `ADAPTIVE_EF`（[[BEH-033]]）与 `LEARNED_EF`（[[BEH-034]]）
- 验证两者在真实 I/O bound 下的增益是否成立
- **验收**：给出 sustained 场景下的真实增益数字

### R6：hnswlib 对照
- 相同多轮采样协议下测 hnswlib unlimited
- **验收**：sustained 场景下的内存-性能 Pareto 对比

## 5. 晋升条件

若以下全部满足，另开 promote 提案：

1. recall ≥ 95%（sustained 场景，官方 GT）
2. cache 饱和曲线清晰可复现（同 seed 结果稳定，±3%）
3. sustained QPS 数字可作为新 SLA 基线候选
4. `ADAPTIVE_EF` / `LEARNED_EF` 在 sustained 场景下的增益得到确认或否证

若 recall < 95% 无法通过调参解决 → 走 §6.2d 负结果闭环。

## 6. 写入边界

- 本 POC MUST NOT 修改 Trunk `src/`
- 所有实现在 `poc/sustained-query-benchmark/`
- 新增条款 `status=draft` / `level=tbd`
- MUST NOT 写入 `status=stable` 的 CON-SLA must（[[CON-POC-001]]）

## 7. 表面冲突检查

活跃 exploring 主题扫描结果：**无活跃 exploring 主题**（全部 promoted/rejected/closed）。

本主题 `explore_surface: test-infra,benchmark-methodology`：
- 与已 promoted 的 `cgroup-v1-support`（surface: test-infra,cgroup）相交于 `test-infra`
- 判定：**不冲突**。cgroup-v1-support 提供内存隔离工具层（`cgroup_utils.sh`），
  本主题在其之上构建 query 采样方法论，是叠加而非竞争关系。
- 本主题 MUST 复用 `scripts/cgroup_utils.sh`（[[API-016]]）

## 8. 影响的既有条款

本 POC 若成功，将影响以下 stable SLA 的解释（但 POC 阶段 MUST NOT 修改）：

| 条款 | 影响 |
|------|------|
| [[CON-SLA-014]] | 512MB SLA 数字为 cache-warmed，需 sustained 对照 |
| [[CON-SLA-016]] | 256MB SLA 同上 |
| [[CON-SLA-017]] | 512MB 16T A2+C2 SLA 同上 |
| [[CON-SLA-018]] | 256MB BG+Merge SLA 同上 |

修改 stable SLA 需在 promote 阶段另开提案。

## 9. 数据文件

| 文件 | 来源 | 大小 |
|------|------|------|
| `sift_query.fvecs` | sift.tar.gz | 10,000 × 128 (5.1MB) |
| `sift_groundtruth.ivecs` | sift.tar.gz | 10,000 × 100 (4MB) |

下载源：`ftp://ftp.irisa.fr/local/texmex/corpus/sift.tar.gz`（168MB，已验证可达）
