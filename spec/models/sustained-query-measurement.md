# MODEL: Sustained query measurement（语义核）

> role: L3-reference（金标 / 行为预言机）
> 由 [[BEH-035]] 与 [[CON-SLA-019]] 经 `model=` 引用；证据与决策见 [[DEC-084]]；
> 测法验收由 [[VER-043]] / [[CON-SLA-014]] / [[CON-SLA-020]]
> **不是** poc 切片、不是 git patch 账本（[[ARCH-008]]）

## Sustained 查询测量参考模型 {#MODEL-SUSTAINED-001}
<!-- ndf: kind=def level=must layer=L3 status=stable since=0.9.10 source=deduced -->
<!-- ndf: depends-on=DEC-084,API-019,CON-SLA-014 -->

本模型定义**声称 disk-resident sustained 吞吐**的测量语义。

存在多个 harness 时（`benchmark_diskhnsw` / `benchmark_sustained` /
`benchmark_hnswlib_native`），其 QPS 与 recall 数字**仅在遵循同一模型时可横向比较**。
语义争议以本条为预言机；具体数字属 [[DEC-084]] / [[CON-SLA-020]]，不属本条正文。

---

### 启用

同时满足时本模型生效：

1. 测量目标是 **disk-resident / 内存受限** 场景下的吞吐或延迟
2. 结果将用于 SLA 验收、对外声明、或跨实现/跨配置比较

**不适用**：纯 in-memory 上限探查（此时 MUST 显式标注口径为 `cache-warmed`，
且 MUST NOT 与 sustained 数字同表并列而不注明）。

---

### 时机（计时窗口边界）

```text
[ 环境准备 ]  sync; drop_caches; 进入 cgroup(memory.max)     ← CON-SLA-014
[ 索引加载 ]  mmap/open、CSR 构建、PQ 载入、slot table 构建    ← 不计入计时
[ 可选预热 ]  仅 CPU 频率 spin；或 disjoint query 集合的 warmup 轮
──────────── 计时窗口开始 ────────────
[ 统计轮 1..R ]  每轮采样 → 执行 → 记录
──────────── 计时窗口结束 ────────────
```

**边界不变量**：计时窗口开始时，被测 query 所需的 vecblocks 页 MUST 处于
"尚未因本次测量而被读入"的状态。索引结构（图 CSR / PQ codes）在加载阶段进入内存
是**合法**的，因其为 query-无关的常驻状态。

---

### 操作

#### 1. 采样

对第 `i` 轮（`i` 从 1 计）：

```text
seed_i = seed_base + i
从 pool 中无放回随机抽取 N 个 query
```

- 轮内 MUST 无放回；轮间 MAY 重复
- `seed_base` MUST 可由调用者指定，默认固定值（保证默认可复现）

warmup 轮 `w`（若启用）：

```text
seed_w = seed_base + 1_000_000 + w
```

即 warmup seed 空间 MUST 与统计轮 **disjoint**。

#### 2. 采样池来源

```text
pool ← 标准 query set（独立采集，与 base 无交集）
gt   ← 该 query set 的官方 groundtruth
```

MUST NOT 从 base 抽样构造 pool。

#### 3. 禁预热

计时窗口内与之前 MUST NOT 对被测 query 执行"先跑一遍"式预热。
允许的预热仅限本模型「时机」段列出的两项。

#### 4. 聚合

```text
qps_agg    = Σ(queries_i) / Σ(elapsed_i)
recall_agg = Σ(hits_i) / Σ(k × queries_i)
qps_steady = qps_R              （末轮，稳态代理）
```

MUST 同时报告 `qps_agg` 与 `qps_steady`。

---

### 不变量

以下不变量是本模型的**判别式**：违反其一即说明测量受 harness 伪影污染，
结果 MUST NOT 用作 SLA 依据。

#### I1. 稳态与采样规模无关

```text
qps_steady(N=N₁) ≈ qps_steady(N=N₂)   ∀ N₁,N₂ 使 R×N 足以达到稳态
```

若改变 `N` 导致稳态 QPS 显著漂移，说明测的不是物理量而是 harness 行为。

> 实证：N=200/1000/10000 稳态收敛于同一区间（[[DEC-084]]）。

#### I2. 同 seed 可复现

同 `seed_base` + 同配置 + 同 Trunk 树 → QPS 在噪声范围内一致。

#### I3. R=1 退化等价

`R=1` 且采样恰好覆盖某固定 query 集时，recall MUST 等价于对该集合的单次测量。
（QPS 不要求等价 —— 单次 harness 若含 query 预热则必然更高，这正是本模型要暴露的差异。）

#### I4. recall 基于官方 GT

recall MUST 以 pool 的官方 groundtruth 为准。

**推论（重要）**：若 pool 来源被污染（如 base-sampled 导致 GT 含 self-match），
则不仅 recall 失效，**任何以该 pool 训练/校准的组件**（模型、阈值、启发式参数）
亦 MUST 视为失效，需以合规 pool 重新校准。

> 实证：GBDT 学习式剪枝（[[BEH-034]]）因训练标签取自 base-sampled pool
> 而收益归零（[[DEC-084]]）。

#### I5. 口径不可混比

`cache-warmed` 与 `sustained` 两种口径的 QPS MUST NOT 直接比较或混入同一趋势图，
除非每个数据点都标注了口径。

#### I6. 跨实现同池同 GT

比较不同实现（如 DiskHNSW vs hnswlib）时，MUST 使用同一 pool 与同一 GT，
且各自遵循本模型的时机与禁预热规则。内存口径 MUST 说明
（cgroup 预算 vs 进程 RSS，见 [[CON-HONEST-002]]）。

---

### 非目标

1. 本模型 **不规定** 任何 QPS / recall 数字（属 [[DEC-084]] / [[CON-SLA-020]]）。
2. 本模型 **不规定** 具体 CLI（属 [[API-019]]）或脚本实现。
3. 本模型 **不替代** VER（[[VER-043]] 负责"如何证明"）。
4. 本模型 **不规定** `R` 与 `N` 的取值 —— 只要求满足 I1（达到稳态）。

> rationale: 从 sustained-query-benchmark R0–R6 蒸馏。造核的直接动因是
> 同一指标曾用三种口径测量（200q+warmup / base-sampled / 官方池）却被横向比较，
> 导致 GBDT 收益结论错误。契约在 [[BEH-035]] / [[CON-SLA-019]]，预言机在此，
> 时间轴在 git，探索史在装订器 —— 四者分离。
> source: poc/sustained-query-benchmark/ndf/TOPIC.md ; evidence/r0..r6 @ 4a33f38
