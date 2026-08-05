# Constraints — SLA / 诚实 I/O

> 条款索引: `CON-SLA-008`, `CON-SLA-009`, `CON-SLA-010`, `CON-HONEST-002`, `CON-SLA-011`, `CON-SLA-012`, `CON-SLA-013`, `CON-SLA-014`, `CON-SLA-015`  
> CON-POC-001 正文在 `spec/meta/constraints.md`（adopted 见下文）

## Page Search SLA 豁免 {#CON-SLA-008}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.2 source=deduced -->
<!-- ndf: refines=DEC-017,CON-007 -->

当 `PAGE_SEARCH=1` 时，Buffered QPS SLA 放宽为 ≥ **现行严格隔离对齐基线** × 85%
（基线见 [[CHR-006]] 观测表 / [[DEC-066]]；白嫖 era 的 1832/2051 仅作历史参考）。
recall SLA 不变（≥ 95%）。

当 `PAGE_SEARCH=0`（默认）时，Buffered QPS 不以 must 下限考核，对齐 [[CHR-006]] 观测基线。
Honest / O_DIRECT 观测基线见 [[CON-SLA-011]]。

> rationale: Page Search 是 opt-in recall 提升功能，用部分 QPS 换 recall。
> 适合 recall 优先于速度的场景。参见 [[DEC-020]]。旧「≥2000」口径经 [[DEC-066]] 废止。

## Dynamic Width 已知限制 {#CON-SLA-009}
<!-- ndf: kind=info level=may layer=L1 status=deprecated since=0.2 source=deduced -->
<!-- ndf: refines=DEC-019,CON-007 depends-on=DEC-024 -->

Dynamic Width 在当前配置（REFINE_EF=100, PQ 粗筛）下无效果。根因：PQ 近似距离的
浮点波动导致 top-K 持续抖动，收敛检测（hash + lowerBound delta）从未触发。

**不纳入 SLA 考核**。代码保留默认关闭（`DYNAMIC_WIDTH=0`），零开销。[[DEC-024]] 已正式放弃；
对应行为条款 [[BEH-015]] 为 `deprecated`。

未来方向：如果 REFINE_EF 降到 30-50，或改用精确距离搜索，DW 可能生效。

## 冷 I/O 模式 SLA {#CON-SLA-010}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.3 source=deduced -->
<!-- ndf: refines=DEC-021 -->

当 `EVICT_PAGE_CACHE=1` 时（**注**：实现侧该变量为幽灵/no-op，真驱逐见 `FINE_FADVISE`；
SoT 对齐另案。本条款 QPS 数字属白嫖 era，**待按 [[CON-SLA-014]] / [[DEC-066]] 重标定**）：
- Recall SLA 不变（≥ 95%）
- Buffered QPS SLA 放宽阈值 **暂不适用**（旧 ≥500 相对热态 ≥2000，口径已废止）
- RSS SLA 对齐 [[CHR-006]]（1T≤300 / 4T≤450）

| 参数 | 默认值 | 环境变量 | 说明 |
|------|--------|---------|------|
| Page Cache 驱逐开关 | `0` (关) | `EVICT_PAGE_CACHE` | 1=每次查询后 posix_fadvise(DONTNEED) 驱逐 vecblocks |

> rationale: 冷 I/O 下 Fine Rerank 每页读取 ~10-50μs（vs 热态 ~1μs），
> QPS 下降是预期行为。QPS ≥ 500 对应 < 2ms/query，仍为交互式可用。

## 诚实 I/O 基准协议 {#CON-HONEST-002}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.5 source=deduced -->
<!-- ndf: refines=DEC-039,DEC-059 depends-on=DEC-057,DEC-062,DEC-065 -->

性能基准测试 MUST 至少报告两组数据：
1. **Buffered**: `FINE_BUFFERED=1`（含 page cache）
2. **Direct**: `FINE_DIRECT=1`（O_DIRECT，无 page cache）

两组模式 MUST 在同一 cgroup 限制下运行。Buffered 模式下，page cache 计入
cgroup 内存使用，运行过程中峰值内存（anon + file）MUST NOT 超过 cgroup 限制。

**cgroup 预算约束（[[DEC-059]] 确立，[[DEC-062]] 修正优先级叙事）**：page cache 与
匿名内存共享 cgroup `memory.max` 预算。可用 page cache 预算 = `memory.max - RSS`。
在运行过程中加载的 page cache 不得使总内存（anon + file）超过限制，否则触发 OOM kill
或 memory reclaim。随数据规模增大，page cache 对 vecblocks 的覆盖率趋近于 0：

| 规模 | cgroup | RSS (参考) | 可用 page cache | vecblocks | 覆盖率 |
|------|--------|------------|----------------|-----------|-------|
| SIFT1M 1T | 512MB | ~235–269MB | ~240MB | 496MB | ~48%（预算理论）；严格隔离下常被 reclaim |
| SIFT1M 4T | 512MB | ~416MB | 更紧 | 496MB | anon 上升挤压 file（[[DEC-066]]） |
| DEEP10M | 2GB | 1612MB | ~390MB | 3.7GB | ~10% |
| 100M (预估) | 4GB | ~2GB | ~2GB | ~50GB | ~4% |

**定位（[[DEC-062]]）**：Buffered（含预算内 page cache）是**生产优化主目标**；
O_DIRECT 是**诚实验收地板**与大规模下**必然磁盘 I/O** 的独立优化路径，不是「唯一 /
第一」生产优化优先级。page cache 在剩余预算内是合法核心加速层，但可用量有限。
抬高地板与 Buffered 流水线的工程路线图见 [[DEC-060]]（非本条款 SLA）。

报告 MUST 标注测量模式。仅报告 Buffered 模式数字时 MUST 附带声明：
"此数字在 cgroup 限制内运行，page cache 与匿名内存共享内存预算"。

所有 SLA 验收 benchmark MUST 按 [[CON-SLA-014]] 严格 cgroup 隔离协议执行，
确保 page cache 在 cgroup 预算内诚实积累，不偷用预算外内存。

> rationale: cgroup v2 的 memory.max 同时限制匿名内存和 page cache。Page cache
> 不是免费资源——它与 RSS 竞争同一块预算。Buffered 是生产推荐路径与优化主战场；
> O_DIRECT 消除 page cache 后测量纯磁盘 I/O 地板，并服务 miss 路径。
> 关联决策: [[DEC-059]]、[[DEC-062]]、[[DEC-060]]、[[DEC-065]]

## Honest / O_DIRECT QPS 下限 {#CON-SLA-011}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.5 source=deduced -->
<!-- ndf: refines=CON-HONEST-002 depends-on=DEC-039,DEC-057,CON-SLA-014,DEC-067 -->

SIFT1M、512MB cgroup、`FINE_DIRECT=1`（Honest / O_DIRECT）、**[[CON-SLA-014]] 严格隔离**下：

| 指标 | 下限 | 严格隔离实测 (2026-08-03, [[DEC-067]]) |
|------|------|----------------------------------------|
| QPS (单线程) | ≥ 100 | **837** |
| QPS (4 线程) | ≥ 400 | **3215** (recall=13.95%⚠️ 待查) |
| Recall@10 | ≥ 95% | 95.75% (1T) / 13.95%⚠️ (4T) |

> DEC-066 假基线（22.8/19.5）因 PQ_CODES_PATH 拼写错误废止，见 [[DEC-067]]。
> 旧 SLA 下限在严格隔离下仍然有效（1T 实测 837 >> 100）。

Buffered 模式阈值仍以 [[CHR-006]] 为准，MUST NOT 用本条款覆盖。

> rationale: 双轨 SLA 保留。严格隔离验证确认旧下限仍然有效。

## Read Coalescing SLA (已废弃) {#CON-SLA-012}
<!-- ndf: kind=constraint level=may layer=L1 status=deprecated since=0.6 source=deduced -->
<!-- ndf: refines=CON-SLA-011 depends-on=DEC-060,BEH-017 -->

> **Deprecated (2026-07-31):** 代码已回退，SLA 不再生效。见 [[BEH-017]] 和 [[DEC-061]]。

## I/O Pipelining SLA (探索轨) {#CON-SLA-013}
<!-- ndf: kind=constraint level=tbd layer=L1 status=deprecated since=0.8 source=deduced topic=io-pipelining -->
<!-- ndf: refines=CON-SLA-011 depends-on=DEC-060,DEC-062,BEH-021,BEH-022,BEH-023,CON-POC-001 deprecated-by=DEC-071 -->

> **track: poc | status: draft | topic: io-pipelining**  
> 装订器: `poc/io-pipelining/ndf/TOPIC.md`；提案 `spec/open/proposal-io-pipelining.md`
> （r3：Buffered 主目标，对齐 [[DEC-062]]）。  
> POC 阶段不纳入生产 SLA（[[CON-POC-001]]）。以下为 POC 验证目标，非 must 承诺。  
> **v1 smoke（~24 QPS、无诚实 cgroup）不可信，MUST NOT 引用为 R0 或增量证据。**  
> L4 **主动管理**（驱逐/保留）见独立草案 [[BEH-024]] / topic `l4-cache-mgmt`，
> **不**纳入本条款 depends-on（证据未叠面前避免绑死）。关闭主题前勿写入 `status=stable` must。
>
> 分层验证 (R0–R4)：**以 Buffered 为核心对比组**；O_DIRECT 为辅助地板组。
>
> | 轮次 | 配置 | 验证目标 |
> |------|------|----------|
> | R0 | 基线 (PIPE_FINE=0) | 锚定基线；须对齐 §7 纪律（见提案 / NOTES） |
> | R1 | + L5 only (PIPE_FINE=1) | pipe_ring_ I/O 重叠 / 主动填 L4 的独立贡献 |
> | R2 | + L5 + L1 (PIPE_FINE=1, PIPE_L1=1) | CPU cache 预取增量 |
> | R3 | + L5 + L4 (PIPE_FINE=1, PIPE_L4=1) | L4 旁路填充跨 query 效果 |
> | R4 | + L5 + L4 + L1 (全开) | 叠加上限 |

### 主表：Buffered（生产优化主目标）

| 指标 | 基线锚点 (参考) | POC 目标 (相对 R0) | 说明 |
|------|----------------|-------------------|------|
| SIFT1M 1T QPS | **2309**（[[CON-SLA-014]] / [[DEC-067]]） | ≥ R0 × 1.03 | 旧 22.9 为 PQ_CODES_PATH 拼写错误，已废止 |
| SIFT1M 4T QPS | **6060**（同上） | ≥ R0 × 1.02 | 旧 18.4 同上 |
| Recall@10 | ≥ 95% | ≥ 95% (不变) | 预取不改变候选集 |
| RSS 增量 | - | ≤ +1MB | pipe_ring_ buffer pool |

### 辅表：O_DIRECT（诚实地板 / 必然 I/O）

| 指标 | 基线 (O_DIRECT) | POC 目标 | 说明 |
|------|-----------------|----------|------|
| SIFT1M 1T QPS | **837**（[[DEC-067]]） | ≥ R0 × 1.03 | 旧 22.8 为 PQ_CODES_PATH 拼写错误，已废止 |
| SIFT1M 4T QPS | **3215**（同上） | ≥ R0 × 1.02 | recall=13.95%⚠️ 待查 |
| DEEP10M 4T QPS | TBD（待严格隔离重测） | TBD | 旧 169 未按 [[CON-SLA-014]] |

### 证据状态（历史；待 [[CON-SLA-014]] 重测前不得 promote）

| 场景 | 结论 | 口径 |
|------|------|------|
| SIFT1M R0–R4 Buffered（旧） | 负结果 | **口径过期**；须按 DEC-066 基线重开 |
| DEEP10M pre/post-memopt pipe | 正/负混杂 | EVICT 幽灵 + 未严格隔离；搁置 |
| 2026-08-03 SIFT1M 严格基线 | 对齐锚点已立 | [[DEC-066]]；pipe POC 见 open 提案 r2 |

> 若 POC 在严格隔离下验证通过，promote 时再评估是否把抬升后的 QPS 写入 must。
> 负结果走 [[BEH-020]]。

## POC 不纳入生产 SLA（adopted）

> **非 SoT 正文** — adopted 指针。Canonical:
> [`../meta/constraints.md#CON-POC-001`](../meta/constraints.md#CON-POC-001)（CON-POC-001）。  
> 见 [`../meta/decisions/adr-meta-layer-split.md`](../meta/decisions/adr-meta-layer-split.md)。


## 严格 cgroup 隔离测试协议 {#CON-SLA-014}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.9 source=deduced -->
<!-- ndf: refines=CON-HONEST-002 depends-on=DEC-065 -->

> **一等公民**：本协议是 Trunk 验收与 POC 对齐的强制测法（[[CHR-006]]、[[CON-HONEST-002]]、
> [[CON-SLA-011]]）。白嫖对照组（未 `drop_caches`）结果 MUST NOT 作为验收或优化证据。
> 白嫖 era QPS 经 [[DEC-067]] 验证在严格隔离下仍然有效；SIFT1M 严格隔离实测已写入 [[CHR-006]]。
> DEEP10M 严格隔离基线仍待 [[VER-039]]。

所有 SLA 验收 benchmark MUST 在严格 cgroup 隔离条件下执行。

**协议**：
1. benchmark 启动前 MUST 执行 `sync && echo 3 > /proc/sys/vm/drop_caches` 清空 page cache
2. benchmark 进程 MUST 运行在受限 cgroup 内（`memory.max` = SLA 规定值）
3. benchmark 启动后所有文件 I/O 为首次读取，page cache 在 cgroup 内记账积累
4. 测试过程中 MUST 监控 `memory.current`、`memory.peak`、`memory.stat`（anon/file）
5. `memory.events` 中 `oom` MUST = 0（不得触发 OOM）

**模拟场景**：此协议模拟真实部署——数据准备在内存充足机器上完成，
文件拷贝到内存受限机器上进行检索。部署机器上无预热的 page cache。
`drop_caches` 将 page cache 状态重置到等价于"文件刚到达"的初始态，
使 cgroup 记账准确。page cache 在预算内合法积累，不被消灭。

**白嫖对照组**：允许额外运行"未清场"组用于对比分析，但其结果
MUST NOT 作为 SLA 验收依据。

**验收报告 MUST 包含**：
1. cgroup `memory.peak`（证明总内存未超限）
2. cgroup `memory.stat` 中的 `anon` 和 `file` 分项（证明 page cache 在预算内）
3. `memory.events` 中的 `oom` 计数（证明未触发 OOM）
4. [可选] `fincore`/`vmtouch` 文件缓存验证

> rationale: cgroup v2 page cache 记账规则为"首次读取者归属"。
> 当数据准备（root cgroup）和检索（子 cgroup）在同一台机器上执行时，
> 数据准备阶段预热的 page cache 不会被重新记账到 benchmark cgroup，
> 导致 benchmark 实际可用内存远超 cgroup 限制，性能数字虚高。
> `drop_caches` 清场模拟了跨机器部署场景，确保 cgroup 记账准确。
> page cache 在 cgroup 预算内（limit - RSS）是核心合法加速层，
> 本协议保障其在预算内被诚实利用。提案见 `spec/open/proposal-strict-cgroup-test.md`。

## SIFT1M 紧凑 cgroup 配置 SLA {#CON-SLA-015}
<!-- ndf: kind=constraint depends-on=CON-SLA-014,DEC-070,BEH-024 source=observed -->

SIFT1M 在 **256MB cgroup**（[[CON-SLA-014]] 严格隔离）+ `L4_WILLNEED=1` + `FLAT_VEC_MB=64`
配置下的性能下限：

| 指标 | 基线 (2026-08-05) | SLA |
|------|-------------------|-----|
| SIFT1M 4T QPS | 8,838 | ≥ 5,000 |
| SIFT1M 4T Recall@10 | 95.80% | ≥ 95% |
| cgroup `oom` | 0 | = 0 |
| cgroup `memory.peak` | 256MB | ≤ 256MB |

**配置**: `L4_WILLNEED=1 FINE_PREAD=1 FLAT_VEC_MB=64 CACHE_MB=64 REFINE_EF=100 NUM_THREADS=4`

**用途**: 内存极度受限场景（嵌入式/多租户），memory 效率 2.0x vs hnswlib unlimited。

**证据**: `poc/perf-gap-4t/ndf/evidence/d6-256mb-cgroup-20260805.md`
