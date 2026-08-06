# TOPIC: sustained-query-benchmark

> topic_id: sustained-query-benchmark
> status: promoted
> baseline_protocol: [[CON-SLA-014]] + [[CON-SLA-019]] + 官方 SIFT1M query 池；基线见 [[CON-SLA-020]] / [[DEC-084]]
> explore_surface: test-infra,benchmark-methodology
> baseline_trunk_sha: 4a33f38
> baseline_status: stale
> depends_on_topics: (none)
> conflicts_with_topics: []
> binder: [[DEF-022]] / [[BEH-025]]
> opened: 2026-08-06
> promoted: 2026-08-06 (DEC-084)

## 目标

建立多轮随机采样持续查询基准，同时破除 200q cache-warmed 假象与
base-sampled query 的 self-match 污染，为真实 I/O bound 场景提供可信 SLA 基线。

## 背景

| 缺陷 | 证据 | 后果 |
|------|------|------|
| 200q cache-warmed | warmup 预热被测 query | QPS 高估 1.73–7.60× |
| base-sampled self-match | GT top-1 恒为 self（距离 0） | recall 虚高；且污染 GBDT 训练标签 |

已据此撤除 `CON-SLA-019` / `CON-SLA-020`（commit `4a33f38`）。

## 方案

标准 SIFT query 池（10,000 官方 query + 官方 GT）+ 每轮随机采样 N 个 + 共 R 轮，
**取消 query warmup**（warmup 被测 query 正是假象来源）。

## Draft clauses

已全部 promote 到 Trunk（[[DEC-084]]）：

| ID | 原状态 | Trunk 位置 | 现状态 |
|----|--------|-----------|--------|
| [[BEH-035]] | draft | `spec/20-behavior/test-infra.md` | **stable / must** |
| [[API-019]] | draft | `spec/30-interfaces/cli.md` | **stable / must** |

同时新增（非 draft 源）：[[CON-SLA-019]]、[[CON-SLA-020]]、[[MODEL-SUSTAINED-001]]、
[[VER-043]]、[[VER-044]]、[[DEC-084]]。

## 数据文件

| 文件 | 说明 |
|------|------|
| `data/sift_query_official10k.fvecs` | 官方 10,000 query (采样池) |
| `data/sift_groundtruth_official.ivecs` | 官方 GT (10,000 × 100) |
| `data/sift_gt_official10k_k10.bin` | 官方 GT 转 k=10 内部格式（hnswlib 用） |

R0 验证结论：现有 200q 是官方池前 200 个（精确匹配），无 self-match。
官方 GT 与现有 gt200 仅 2 行 exact-tie 差异（dist² 完全相同）。

## 实验矩阵

| 轮次 | 内容 | 状态 |
|------|------|------|
| R0 | 标准数据集下载 + 一致性验证 | ✅ [evidence](evidence/r0-dataset-verification-20260806.md) |
| R1 | 多轮 benchmark 实现 + 等价性验证 | ✅ [evidence](evidence/r1-r2-saturation-20260806.md) |
| R2 | cache 饱和曲线（N=200, R 扫描） | ✅ 同上 |
| R3 | 规模扫描（N ∈ 200/1000/10000） | ✅ [evidence](evidence/r3-r5-sweep-20260806.md) |
| R4 | cgroup 扫描（256MB/512MB × 1/4/16T） | ✅ 同上 |
| R5 | ADAPTIVE_EF / LEARNED_EF sustained 复测 | ✅ 同上 |
| R6 | hnswlib 对照 | ✅ [evidence](evidence/r6-hnswlib-comparison-20260806.md) |

## 核心结论

### 1. 方法论有效 ✅

- R=1 recall 与现有 baseline **精确一致**（95.75%）→ 逻辑正确
- 稳态 QPS **与 N 无关**（N=200/1000/10000 均收敛到 1,649–1,722）→ 测的是物理量
- recall **96.00%** ≥ 95% 商用门槛 → 可作为 SLA 依据
- 同 seed 可复现（±0.2%）

### 2. 饱和曲线方向与提案预期相反（提案已证伪并修正）

实测 QPS 从冷启动 ~245 单调**上升**至稳态 ~1,670，R≈20 饱和。

根因：随机换 query **无法驱逐 query-无关共享状态**
（图 CSR 47MB + PQ codes 30MB + FVC 160MB ≈ 237MB，512MB 预算内长期驻留）。
真正的假象来源是 **warmup 预热被测 query 本身**，而非 working set 规模。

### 3. cache-warmed 高估倍数（诚实对照）

| 配置 | 现 SLA (200q+warmup) | sustained 稳态 | 高估 |
|------|---------------------|---------------|------|
| 512MB 1T | 3,241 | 1,729 | 1.87× |
| 512MB 4T | 9,090 | 5,247 | 1.73× |
| 512MB 16T | 30,332 | 6,694 | 4.53× |
| 256MB 4T | 8,838 | 2,519 | 3.51× |
| 256MB 16T | 18,675 | 2,456 | 7.60× |

### 4. ADAPTIVE_EF (BEH-033) 有效 ✅

sustained 下 **+12.5% ~ +31.4%**，recall 95.80–95.81%（≥95%）。
且 512MB 下也有收益 —— **推翻**此前"512MB 无收益"的 cache-warmed 判断。

### 5. GBDT / LEARNED_EF (BEH-034) 收益证伪 ❌

sustained 下 **−0.9% ~ +1.8%**（噪声内），此前声称的 +33~124% 不成立。

根因：GBDT 训练数据来自 base-sampled 10K query 的 profiling，
那批 query 因 self-match 而"异常容易"，模型学到的候选数分布系统性偏低。
**self-match bug 不仅污染 recall 指标，还污染了 GBDT 的训练标签。**

在线自适应信号（ADAPTIVE）对分布漂移鲁棒；离线学习模型（GBDT）对训练集质量敏感。

### 6. QPS/MB 内存效率优势不成立 ❌

sustained 下 DiskHNSW QPS/MB 为 hnswlib 的 0.17–0.33×，
此前 1.10×/1.36× 的优势来自 cache-warmed 测量。

真实定位：**能在内存不足时工作** + **绝对内存占用低（33%）**，
但吞吐代价显著（5.7–26.9% of hnswlib）。

## 晋升条件核对

| 条件 | 结果 |
|------|------|
| recall ≥ 95% | ✅ 96.00% |
| 饱和曲线可复现 | ✅ ±0.2% |
| sustained QPS 可作 SLA 候选 | ✅ 完整矩阵 |
| ADAPTIVE/LEARNED 增益确认或否证 | ✅ ADAPTIVE 确认；GBDT 否证 |

**全部满足 → ready-for-promote**

## 后续需处理（promote 阶段）

全部已完成（见 [[DEC-084]] §9）：

- [x] 新增 sustained SLA 条款 → [[CON-SLA-020]]
- [x] 现有 `CON-SLA-014/016/017/018` 标注 cache-warmed 口径
- [x] `BEH-034` / `API-018`（GBDT）收益修正：must → **may**，删除 "+33~124%"
- [x] `BEH-033`（ADAPTIVE）补 512MB 收益，删除“512MB 无收益”误判
- [x] 语义核 [[MODEL-SUSTAINED-001]] 交付并挂 `model=`
- [ ] README / detailed-design 的 QPS/MB 效率声明修正（全面测试后执行）

## 归档

本装订器保留在 `poc/sustained-query-benchmark/ndf/` 作为复现入口（摘要指针方式），
不整包迁入 `spec/archive/`，因：
1. 本主题产出的是**测量工具**，后续会持续使用（DEEP10M 等）
2. `benchmark_sustained.cpp` 已合入 Trunk `src/benchmark/`，poc 副本仅作历史对照
3. evidence 被 [[DEC-084]] 与 [[VER-043]] 直接引用，保持路径稳定更优

## Proposals

| Role | Path | Status |
|------|------|--------|
| POC 提案 | `spec/open/proposal-sustained-query-benchmark.md` | Implemented 2026-08-06 |
| Draft 条款 | `ndf/proposals/draft-clauses.md` | Promoted 2026-08-06 |
| Promote 提案 | `spec/open/proposal-promote-sustained-query-benchmark.md` | Implemented 2026-08-06 |

## 装订

| Role | Path | Status |
|------|------|--------|
| 实现 | `benchmark_sustained.cpp` + `Makefile` + `run_sustained.sh` | done |
| 证据 | `ndf/evidence/r0,r1-r2,r3-r5,r6` | done |
| Commits | `ndf/COMMITS.md` | done |

## 表面冲突

活跃 exploring 主题：无（开题时全部 promoted/rejected/closed）。

与已 promoted `cgroup-v1-support`（test-infra,cgroup）相交于 `test-infra`：
判定不冲突 —— 本主题复用其 `cgroup_utils.sh`（[[API-016]]）作为隔离层，叠加关系。

## 影响的 stable 条款（POC 阶段未修改）

`CON-SLA-014` / `CON-SLA-016` / `CON-SLA-017` / `CON-SLA-018` — cache-warmed 口径
`BEH-034` / `API-018` — GBDT 收益描述与 sustained 实测矛盾

修改需 promote 阶段另开提案。
