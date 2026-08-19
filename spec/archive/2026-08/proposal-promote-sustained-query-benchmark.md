# 提案：promote sustained-query-benchmark（真实持续查询测量方法论）

> track: promote
> Topic: sustained-query-benchmark
> 装订器: `poc/sustained-query-benchmark/ndf/TOPIC.md`
> 基线 Trunk: `4a33f38`；POC 实现 commit: `47ed9e7`
> 提出日期: 2026-08-06
>
> **Status: Implemented on 2026-08-06**
>
> 用户已确认全部 5 项。执行结果见 §10 与 `poc/sustained-query-benchmark/ndf/COMMITS.md`。
> 条款计数 217 → 225；graphcheck 0 error；VER-043 复现偏差 0.2%。
> source: poc/sustained-query-benchmark/ndf/TOPIC.md ; proposals/draft-clauses.md ; evidence/ ; COMMITS.md @ 4a33f38

---

## 1. 动机

现行全部性能 SLA（`CON-SLA-016` / `CON-SLA-017` / `CON-SLA-018`）建立在
`benchmark_diskhnsw` 的 200q 测量之上。该 harness 在**计时前把全部待测 query
跑一遍以预热 cache**，导致测得的是 in-memory 性能，而非 disk-resident
设计目标下的真实吞吐。

`CON-SLA-014`（严格 cgroup 隔离）只约束了 benchmark **启动前** `drop_caches`，
**未禁止 benchmark 内部对被测 query 预热** —— 这是协议的漏洞。

POC 实测高估幅度 **1.73–7.60×**（详见 §3）。

## 2. 晋升内容

### 2.1 draft → stable 条款清单

| ID | draft 位置 | 目标 Trunk 位置 | 说明 |
|----|-----------|----------------|------|
| `BEH-035` | `poc/sustained-query-benchmark/ndf/proposals/draft-clauses.md` | `spec/20-behavior/benchmark.md`（新建） | 多轮随机采样持续查询基准行为 |
| `API-019` | 同上 | `spec/30-interfaces/cli.md` | `benchmark_sustained` CLI |

### 2.2 新增条款

| ID | 位置 | 级别 | 说明 |
|----|------|------|------|
| `CON-SLA-019` | `spec/40-constraints/sla.md` | must | **禁止对被测 query 预热**（补 `CON-SLA-014` 漏洞） |
| `CON-SLA-020` | `spec/40-constraints/sla.md` | must | Sustained SLA 基线（SIFT1M，官方 query 池） |
| `DEC-084` | `spec/decisions/20-sustained-benchmark-methodology.md` | — | 方法论决策 + GBDT 收益证伪 |
| `VER-043` | `spec/50-verification/` | — | sustained benchmark 验收 |
| `MODEL-SUSTAINED-001` | `spec/models/sustained-query-measurement.md` | must (L3) | **语义核**（见 §5） |

> 注：`CON-SLA-019` / `CON-SLA-020` 两个 ID 曾在 2026-08-06 短暂使用后撤除
> （commit `4a33f38`，因 self-match bug 导致 recall 89.7% 不达门槛）。
> 本次**复用**这两个 ID，语义完全不同且证据有效。`DEC-083` 保留作认知记录。

### 2.3 修正现有 stable 条款

| ID | 修正内容 | 理由 |
|----|---------|------|
| `CON-SLA-014` | 增加"MUST NOT 预热被测 query"引用 `CON-SLA-019` | 补漏洞 |
| `CON-SLA-016/017/018` | 标注为 **cache-warmed 口径**，附 sustained 对照倍数 | 诚实（`CON-HONEST-002`） |
| `BEH-033`（ADAPTIVE） | 删除"512MB 下收益不明显或略有退化"；补 sustained 实测 +12.5~31.4% | 原判断来自 cache-warmed 测量，已证伪 |
| `BEH-034`（GBDT） | 删除"+33~124% QPS"；`level` must → **may**；标注收益在 sustained 下不成立 | 收益证伪（§4） |
| `API-018`（GBDT 旋钮） | 标注收益状态 | 同上 |

## 3. 证据

### 3.1 方法论有效性

| 检查 | 结果 | 证据 |
|------|------|------|
| R=1 recall vs 现有 200q baseline | **95.75% 精确一致** | `evidence/r1-r2-saturation-20260806.md` |
| 稳态 QPS 与采样规模 N 无关 | N=200/1000/10000 → 1,649 / 1,722 / 1,649（跨度 4%） | `evidence/r3-r5-sweep-20260806.md` |
| recall ≥ 95% 商用门槛 | **96.00%** | 同上 |
| 同 seed 可复现 | ±0.2% | 同上 |
| Trunk `src/` 改动 | **零**（链接未修改 Trunk src） | `ndf/COMMITS.md` |

**稳态与 N 无关**是方法论有效性的核心证据：测得的是物理量，而非 harness 伪影。

### 3.2 cache-warmed 高估倍数

| 配置 | 现 SLA (200q+warmup) | sustained 稳态 | 高估 |
|------|---------------------|---------------|------|
| 512MB 1T | 3,241 | 1,729 | 1.87× |
| 512MB 4T | 9,090 | 5,247 | 1.73× |
| 512MB 16T | 30,332 | 6,694 | **4.53×** |
| 256MB 4T | 8,838 | 2,519 | 3.51× |
| 256MB 16T | 18,675 | 2,456 | **7.60×** |

线程数越高高估越严重 —— warmup 使全部线程命中 page cache，掩盖 I/O 争用。

### 3.3 饱和曲线（修正提案原预期）

原 POC 提案预期"QPS 随轮数下降"，实测**单调上升**：冷启动 ~245 → 稳态 ~1,670，
**R≈20 饱和**。

根因：随机换 query **无法驱逐 query-无关共享状态**
（图 CSR 47MB + PQ codes 30MB + FVC 160MB ≈ 237MB，512MB 预算内长期驻留）。
此前"working set ~10MB / ~488MB"的算法只统计 Phase B 向量页，
**漏掉占主导的共享状态**。

真正的假象来源是 **warmup 预热被测 query 本身**，而非 working set 规模。
→ 这直接决定了 `CON-SLA-019` 的措辞方向（禁预热，而非要求大 working set）。

## 4. GBDT 收益证伪（`BEH-034` 降级依据）

| 场景 | GBDT 增益 | 测量有效性 |
|------|----------|-----------|
| 200q + warmup | +3.3~6.0% | ❌ cache-warmed |
| base-sampled 10Kq | +33~124% | ❌ GT self-match 污染 |
| **官方池 sustained** | **−0.9~+1.8%**（噪声内） | ✅ 诚实 |

**根因**：GBDT 训练数据来自 base-sampled 10K query 的 profiling。那批 query
因 self-match 而"异常容易"（GT top-1 恒为自己，距离 0），模型学到的候选数分布
系统性偏低。用在官方 query 上预测失准 → 收益归零。

> **self-match bug 不仅污染 recall 指标，还污染了 GBDT 的训练标签。**

### 处置：降级而非 rollback

| 选项 | 评估 |
|------|------|
| rollback（revert src） | ❌ 过度。默认 `LEARNED_EF=0`，无生产风险；代码本身正确，是**收益声明**错误 |
| §6.2d 负结果闭环（deprecated） | ⚠️ 偏重。机制可复活（重训练即可） |
| **must → may + 收益声明修正** | ✅ **采纳**。保留机制与代码，只修正不诚实的收益数字 |

`BEH-034` 保留 `status=stable`（接口稳定、行为确定），但 `level` must → **may**，
正文明确：**当前模型收益在 sustained 场景下不成立，需用官方 query 池重新训练**。

同时新增 `DEC-084` 记录证伪与根因。

## 5. 语义核决策（`META-004`）：**要** ✅

### 判定依据

`META-004` §2：「仅当契约欠定、预期重构或**多实现需要对齐**时 SHOULD 蒸馏」。

本主题**三条**成立：

| 依据 | 本主题情况 |
|------|-----------|
| **多实现需对齐** ✅ | 已有 3 个 harness：`benchmark_diskhnsw`（cache-warmed）、`benchmark_sustained`（sustained）、`benchmark_hnswlib_native`（对照）。三者 recall/QPS 口径必须一致才可比，否则重演本次事故 |
| **契约欠定** ✅ | `CON-SLA-014` 只规定 `drop_caches`，未规定"计时边界内允许什么"。本次事故正是欠定所致 |
| **预期重构** ✅ | DEEP10M / 其它数据集将复用此方法论，需要稳定预言机 |

### 为何是语义核而非仅 L1 + VER

测量方法论的争议点是**语义**（什么算 warmup？采样如何保证可复现？recall 基于哪份 GT？），
而非"跑哪个脚本"。VER 只能回答"如何证明"，`model=` 才回答"契约应对齐的参考语义"。

一个反例即证明必要性：本次 GBDT 事故的根源是**三次测量用了三种口径**
（200q+warmup / base-sampled / 官方池），却都被当作"同一个 QPS 指标"横向比较。
有金标预言机时这类错误在设计阶段即可拦截。

### 交付内容

`spec/models/sustained-query-measurement.md` → `MODEL-SUSTAINED-001`

只含 **启用条件 / 时机 / 操作 / 不变量**（`META-004` 内容纪律）：

- **启用**：任何声称 disk-resident sustained 吞吐的测量
- **时机**：`drop_caches` 后、计时窗口的精确边界定义
- **操作**：采样规则（seed 派生、轮内无放回）、禁预热规则、recall 聚合规则
- **不变量**：稳态与 N 无关、同 seed 可复现、recall 基于官方 GT、warmup 轮 seed 必须 disjoint

**MUST NOT** 写入：QPS/recall 具体数字（属 `DEC-084` / `CON-SLA-020`）、
poc 树内容、commit ledger。

### 挂接

```text
BEH-035  model=MODEL-SUSTAINED-001     # 行为条款引用预言机
CON-SLA-019  depends-on=MODEL-SUSTAINED-001
```

## 6. 全面测试计划（promote 后执行）

以 `MODEL-SUSTAINED-001` 为唯一口径，重测全矩阵并刷新 README。

### 6.1 矩阵

| 维度 | 取值 |
|------|------|
| 数据集 | SIFT1M（完整）、DEEP10M（若时间允许） |
| cgroup | 256MB / 512MB / 2GB(DEEP10M) |
| 线程 | 1 / 4 / 8 / 16 |
| 模式 | BASE / ADAPTIVE_EF / LEARNED_EF |
| 对照 | **hnswlib unlimited memory**（同官方 query + 同官方 GT） |
| 参数 | N=1000, R=15（稳态），seed=42 |

### 6.2 hnswlib 对照口径（用户明确要求）

MUST 满足：
1. **同一 query 池**（官方 10K）与**同一 GT**（官方 ivecs 转 k=10）
2. 每组前 `drop_caches`
3. hnswlib 不设 cgroup 上限（unlimited，代表 in-memory 天花板）
4. 报告 QPS / recall / RSS 三元组 + QPS/MB 效率

R6 已得初值：hnswlib 1T 6,424 / 4T 22,757 / 16T 42,947 QPS，recall **98.25%**，RSS 734–763MB。

### 6.3 README 刷新要点（诚实性修正）

| 现声明 | 修正后 |
|--------|--------|
| 512MB 16T = 30,332 QPS | **6,694 QPS**（sustained）；30,332 标注为 cache-warmed |
| QPS/MB = 1.10× hnswlib | **0.23×**（sustained） |
| GBDT +33~124% | **收益不成立**，需重训练 |
| — | 新增：ADAPTIVE_EF sustained +12.5~31.4%（含 512MB） |
| — | 新增：真实定位 = 内存不足时可工作 + 绝对内存低(33%)，吞吐代价 5.7–26.9% |

> `CON-HONEST-002` 要求诚实报告。README 作为对外门面，MUST 以 sustained 口径为主，
> cache-warmed 数字若保留 MUST 显式标注口径。

## 7. 晋升条件核对（`BEH-019`）

| 条件 | 状态 |
|------|------|
| 1. 证据（对齐 `CON-SLA-014` 严格隔离） | ✅ R0–R6，全部 cgroup 隔离 + drop_caches |
| 2. 提案经人工确认 + draft→stable 清单 | ⏳ 本提案，清单见 §2.1 |
| 3. 代码干净合入 `src/` + commit trailers | ⏳ 见 §8 |
| 4. 编译验证 + SLA/VER | ⏳ 见 §8 |
| 5. 装订器收口（TOPIC → promoted, COMMITS 记录, 归档） | ⏳ |
| 6. 语义核决策 | ✅ **要**（§5） |
| 7. 基线失效与表面冲突 | ✅ 无活跃 exploring 主题；`test-infra` 与已 promoted `cgroup-v1-support` 为叠加关系 |

## 8. 执行步骤

1. 新建 `spec/20-behavior/benchmark.md`，`BEH-035` draft → stable
2. `spec/30-interfaces/cli.md` 加 `API-019` stable
3. `spec/40-constraints/sla.md` 加 `CON-SLA-019`（禁预热）+ `CON-SLA-020`（sustained 基线）；
   修正 `CON-SLA-014` 与 `CON-SLA-016/017/018` 口径标注；更新条款索引行
4. `spec/models/sustained-query-measurement.md` 交付 `MODEL-SUSTAINED-001`；
   `BEH-035` 挂 `model=`
5. `spec/decisions/20-sustained-benchmark-methodology.md` 写 `DEC-084`
6. `spec/50-verification/` 加 `VER-043`
7. 修正 `BEH-033`（补 512MB 收益）、`BEH-034` must→may、`API-018`
8. 代码合入 `src/benchmark/benchmark_sustained.cpp` + 构建系统 + `scripts/`
9. 编译验证 + 跑 `VER-043`
10. `ndf_index.py index` + `ndf_graphcheck.py`（MUST 0 error）
11. TOPIC → `promoted`，COMMITS 记 `src_commit` + `spec_commit`，归档装订器
12. **全面测试**（§6）+ README 刷新

## 9. 风险

| 风险 | 缓解 |
|------|------|
| README 数字大幅下调影响项目说服力 | `CON-HONEST-002` 优先；且 ADAPTIVE 收益上调、"内存不足可工作"定位仍成立 |
| `CON-SLA-019/020` ID 复用引起混淆 | 提案与 DEC-084 显式说明复用及语义差异 |
| `BEH-034` 降级被误读为机制失效 | 正文明确：代码正确，是训练集污染；重训练可复活 |
| 全面测试耗时长 | 用 N=1000/R=15（~40s/组）而非跑满 10K |

---

## 待人工确认

- [x] §2 晋升内容与条款清单
- [x] §4 `BEH-034` 处置方式：**must → may + 修正收益声明**（而非 rollback / deprecated）
- [x] §5 语义核决策：**要**，交付 `MODEL-SUSTAINED-001`
- [x] §2.2 `CON-SLA-019` / `CON-SLA-020` ID 复用
- [x] §6 全面测试矩阵与 README 刷新范围

（全部于 2026-08-06 经用户确认）

---

## 10. 执行结果（2026-08-06）

### 条款落地

| ID | 位置 | 状态 |
|----|------|------|
| `BEH-035` | `spec/20-behavior/test-infra.md:40` | stable / must ✅ |
| `API-019` | `spec/30-interfaces/cli.md:197` | stable / must ✅ |
| `CON-SLA-019` | `spec/40-constraints/sla.md:316` | stable / must ✅ |
| `CON-SLA-020` | `spec/40-constraints/sla.md:354` | stable / must ✅ |
| `MODEL-SUSTAINED-001` | `spec/models/sustained-query-measurement.md:8` | stable / L3 ✅ |
| `DEC-084` | `spec/decisions/20-sustained-benchmark-methodology.md:9` | stable ✅ |
| `VER-043` | `spec/50-verification/acceptance-p2.md:145` | stable ✅ |
| `VER-044` | `spec/50-verification/acceptance-p2.md:181` | stable ✅ |

修正：`CON-SLA-014`（第 6 条 + 历史漏洞说明）、`CON-SLA-016/017/018`（cache-warmed 标注）、
`BEH-033`（补 512MB 收益）、`BEH-034`（must→may）、`API-018`（收益状态）。

### 验证

| 项 | 结果 |
|----|------|
| 编译 | ✅ `make build/benchmark_sustained`（仅 Trunk 预存 warning）|
| VER-043 复现 | ✅ 512MB/1T/N=1000/R=15 → **1,482.6 QPS / 96.00% / unique 7,942** |
| vs POC 基线 | ✅ 1,482.6 vs 1,479.5（**0.2%**），recall 与 unique 精确一致 |
| graphcheck | ✅ **0 error**，15 warning（全为预存 unlinked）|
| 条款计数 | 217 → **225** |

### 图修正

初次写入时 `BEH-035 depends-on API-019` 与 `API-019 depends-on BEH-035` 构成环
（graphcheck 1 error）。改为 `API-019 refines API-002`（行为条款单向持有依赖），环消除。

### 代码合入时的修正

1. `CSV_AGG` 补齐 `rounds` 与 `last_round_qps` 字段（[[API-019]] 要求报告末轮 QPS）
2. `Decay:` → `Ramp-up:`（原标签方向错误，实测为上升）
3. `scripts/run_sustained.sh` 新增 **池来源校验**（路径含 `base` 则报错退出，
   机械拦截 [[BEH-035]] 里“MUST NOT 从 base 抽样”的违规）
4. `cg_report`（不存在）→ `cg_stats_summary` + `cg_check_violations`
