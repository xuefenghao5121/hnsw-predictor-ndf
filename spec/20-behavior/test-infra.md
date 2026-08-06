# Behavior — 测试基础设施

> 条款索引: `BEH-032`, `BEH-035`

## cgroup v1/v2 自动检测与严格隔离 {#BEH-032}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.7 source=observed topic=cgroup-v1-support -->
<!-- ndf: depends-on=CON-SLA-014,DEC-079 -->

> **track: promoted** - 提案 `spec/open/proposal-cgroup-v1-support.md`（2026-08-06）。
> 装订器: `poc/cgroup-v1-support/ndf/TOPIC.md`。
> source: poc/cgroup-v1-support/ndf/TOPIC.md ; ../../spec/open/proposal-cgroup-v1-support.md

测试脚本 MUST 通过 `scripts/cgroup_utils.sh` 兼容层操作 cgroup，不得硬编码
特定版本的 cgroup 路径或接口文件名。

兼容层 MUST 自动检测 cgroup 版本（v2 unified / v1 memory controller），
并屏蔽路径、文件名、stat 字段映射差异。

### 严格隔离要求

测试完成后 MUST 执行 `cg_verify()` 双重检查：

1. **峰值检查**: `peak ≤ limit`（v2: `memory.peak`; v1: `memory.max_usage_in_bytes`）
2. **违规检查**: `violations = 0`（v2: `memory.events.oom + oom_kill`; v1: `memory.failcnt`）

**v1 比 v2 更严格**: v1 的 `memory.failcnt > 0` 表示任何内存分配被拒绝（即使未触发 OOM kill），
视为偷用内存未遂。v1 还 MUST 显式禁用 swap（`memsw.limit_in_bytes=0` + `swappiness=0`）。

### 不允许的行为

- 测试脚本 MUST NOT 在 cgroup 限制下跑 benchmark 时跳过 `cg_verify()`
- 测试脚本 MUST NOT 仅检查 RSS 而忽略 file cache（page cache 与 RSS 共享 cgroup 预算）
- 测试脚本 MUST NOT 在 v1 平台上使用 v2 接口路径（静默失败）

> rationale: cgroup v1 和 v2 的接口完全不同（路径/文件名/OOM/stat），硬编码 v2 路径
> 在 v1 平台上会静默失败，导致测试不在真正内存隔离下运行，产生不可信数据。
> v1 failcnt > 0 策略确保任何试图超过限制的内存分配都被捕获。
> source: poc/cgroup-v1-support/ndf/TOPIC.md

## 多轮随机采样持续查询基准 {#BEH-035}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.10 source=observed topic=sustained-query-benchmark trunk-ref=47ed9e7 -->
<!-- ndf: depends-on=API-019,CON-SLA-019,DEC-084 model=MODEL-SUSTAINED-001 -->

> **track: promoted** - 提案 `spec/open/proposal-promote-sustained-query-benchmark.md`（2026-08-06）。
> 装订器: `poc/sustained-query-benchmark/ndf/TOPIC.md`。
> Promotes: sustained-query-benchmark。
> 参考语义（预言机）: [[MODEL-SUSTAINED-001]]。

声称 **disk-resident sustained 吞吐**的 benchmark MUST 支持多轮随机采样模式：
从标准 query 池中每轮随机采样 N 个 query，共执行 R 轮，聚合报告 QPS 与 recall@k。

### 采样约束

1. 采样池 MUST 为**标准 query set**（独立采集），MUST NOT 从 base 抽样。
   > base-sampled query 的 GT top-1 恒为 self（距离 0），recall 虚高约 10%；
   > 且其近邻结构位于数据流形内部，与标准 query 分布不同（[[DEC-084]]）。
2. 采样 MUST 由 seed 控制：第 `i` 轮使用 `seed_base + i`，保证可复现。
3. 轮内采样 MUST 无放回（同一轮不重复 query）；轮间 MAY 重复。
4. recall 计算 MUST 基于该 query set 的**官方 groundtruth**。
5. warmup 轮（若启用）MUST 使用与统计轮 **disjoint** 的 seed 空间，且 MUST NOT 计入统计。

### 计时约束

MUST 遵循 [[CON-SLA-019]]：计时窗口内 MUST NOT 对被测 query 预热。

### 报告约束

1. MUST 报告聚合 QPS（总 query 数 / 总耗时）与聚合 recall@k。
2. MUST 报告**末轮 QPS**（稳态代理值）。
3. SHOULD 报告每轮 QPS，用于观察 page cache 饱和过程。
4. SHOULD 报告累积 unique query 数。

### 与单次 benchmark 的关系

`R=1` 时 MUST 退化为等价于现有单次 benchmark（同 query 集合时 recall 一致）。
已验证：R=1/N=200 recall 95.75%，与 `benchmark_diskhnsw` 精确一致（[[DEC-084]]）。

### 不变量

稳态 QPS MUST 与采样规模 `N` 无关（在噪声范围内）。若 `N` 变化导致稳态显著漂移，
说明测量受 harness 伪影污染而非物理量 —— 详见 [[MODEL-SUSTAINED-001]]。

> rationale: 单次固定 query 集会被 page cache 完全吸收，叠加 harness 内 query 预热后
> 测得的是 in-memory 性能（高估 1.73–7.60×，见 [[DEC-084]]）。多轮随机采样 + 禁预热
> 使测量落在真实 I/O 压力下，同时保持 recall ≥ 95% 商用门槛（实测 96.00%）。
> source: poc/sustained-query-benchmark/ndf/TOPIC.md ; evidence/r1-r2-saturation-20260806.md ; evidence/r3-r5-sweep-20260806.md @ 4a33f38
