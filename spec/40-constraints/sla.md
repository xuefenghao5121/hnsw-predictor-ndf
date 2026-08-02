# Constraints — SLA / 诚实 I/O

> 条款索引: `CON-SLA-008`, `CON-SLA-009`, `CON-SLA-010`, `CON-HONEST-002`, `CON-SLA-011`, `CON-SLA-012`, `CON-SLA-013`, `CON-POC-001`

## Page Search SLA 豁免 {#CON-SLA-008}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.2 source=deduced -->
<!-- ndf: refines=DEC-017,CON-007 -->

当 `PAGE_SEARCH=1` 时，Buffered QPS SLA 放宽为 ≥ 基线 × 85%（当前实测 1832/2051 = 89%，达标）。
recall SLA 不变（≥ 95%，实测 96.20%）。

当 `PAGE_SEARCH=0`（默认）时，Buffered 原始 SLA（QPS ≥ 2000）不变。Honest / O_DIRECT 下限见 [[CON-SLA-011]]。

> rationale: Page Search 是 opt-in recall 提升功能，用 ~15% QPS 换 0.5pp recall。
> 适合 recall 优先于速度的场景。参见 [[DEC-020]]。

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

当 `EVICT_PAGE_CACHE=1` 时：
- Recall SLA 不变（≥ 95%）
- Buffered QPS SLA 放宽为 ≥ 500（冷 I/O 条件下 QPS 自然下降）
- RSS SLA 不变（≤ 300MB）

| 参数 | 默认值 | 环境变量 | 说明 |
|------|--------|---------|------|
| Page Cache 驱逐开关 | `0` (关) | `EVICT_PAGE_CACHE` | 1=每次查询后 posix_fadvise(DONTNEED) 驱逐 vecblocks |

> rationale: 冷 I/O 下 Fine Rerank 每页读取 ~10-50μs（vs 热态 ~1μs），
> QPS 下降是预期行为。QPS ≥ 500 对应 < 2ms/query，仍为交互式可用。

## 诚实 I/O 基准协议 {#CON-HONEST-002}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.5 source=deduced -->
<!-- ndf: refines=DEC-039,DEC-059 depends-on=DEC-057,DEC-062 -->

性能基准测试 MUST 至少报告两组数据：
1. **Buffered**: `FINE_BUFFERED=1`（含 page cache）
2. **Direct**: `FINE_DIRECT=1`（O_DIRECT，无 page cache）

两组模式 MUST 在同一 cgroup 限制下运行。Buffered 模式下，page cache 计入
cgroup 内存使用，运行过程中峰值内存（anon + file）MUST NOT 超过 cgroup 限制。

**cgroup 预算约束（[[DEC-059]] 确立，[[DEC-062]] 修正优先级叙事）**：page cache 与
匿名内存共享 cgroup `memory.max` 预算。可用 page cache 预算 = `memory.max - RSS`。
在运行过程中加载的 page cache 不得使总内存（anon + file）超过限制，否则触发 OOM kill
或 memory reclaim。随数据规模增大，page cache 对 vecblocks 的覆盖率趋近于 0：

| 规模 | cgroup | RSS | 可用 page cache | vecblocks | 覆盖率 |
|------|--------|-----|----------------|-----------|-------|
| SIFT1M | 512MB | 269MB | ~240MB | 496MB | ~48% |
| DEEP10M | 2GB | 1612MB | ~390MB | 3.7GB | ~10% |
| 100M (预估) | 4GB | ~2GB | ~2GB | ~50GB | ~4% |

**定位（[[DEC-062]]）**：Buffered（含预算内 page cache）是**生产优化主目标**；
O_DIRECT 是**诚实验收地板**与大规模下**必然磁盘 I/O** 的独立优化路径，不是「唯一 /
第一」生产优化优先级。page cache 在剩余预算内是合法核心加速层，但可用量有限。
抬高地板与 Buffered 流水线的工程路线图见 [[DEC-060]]（非本条款 SLA）。

报告 MUST 标注测量模式。仅报告 Buffered 模式数字时 MUST 附带声明：
"此数字在 cgroup 限制内运行，page cache 与匿名内存共享内存预算"。

> rationale: cgroup v2 的 memory.max 同时限制匿名内存和 page cache。Page cache
> 不是免费资源——它与 RSS 竞争同一块预算。Buffered 是生产推荐路径与优化主战场；
> O_DIRECT 消除 page cache 后测量纯磁盘 I/O 地板，并服务 miss 路径。
> 关联决策: [[DEC-059]]、[[DEC-062]]、[[DEC-060]]

## Honest / O_DIRECT QPS 下限 {#CON-SLA-011}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.5 source=deduced -->
<!-- ndf: refines=CON-HONEST-002 depends-on=DEC-039,DEC-057 -->

SIFT1M、512MB cgroup、`FINE_DIRECT=1`（Honest / O_DIRECT）下：

| 指标 | 下限 | 实测锚点 (2026-07-31) |
|------|------|----------------------|
| QPS (单线程) | ≥ 100 | 130 |
| QPS (4 线程) | ≥ 400 | 502 |
| Recall@10 | ≥ 95% | 95.70% |

Buffered 模式阈值仍以 [[CHR-006]] Buffered 行及 [[CON-SLA-008]]…[[CON-SLA-010]] 为准，MUST NOT 用本条款覆盖。

> rationale: 双轨 SLA——不静默删除 Buffered 数字；Honest 下限取自 O_DIRECT 实测并留安全余量。

## Read Coalescing SLA (已废弃) {#CON-SLA-012}
<!-- ndf: kind=constraint level=may layer=L1 status=deprecated since=0.6 source=deduced -->
<!-- ndf: refines=CON-SLA-011 depends-on=DEC-060,BEH-017 -->

> **Deprecated (2026-07-31):** 代码已回退，SLA 不再生效。见 [[BEH-017]] 和 [[DEC-061]]。

## I/O Pipelining SLA (探索轨) {#CON-SLA-013}
<!-- ndf: kind=constraint level=tbd layer=L1 status=draft since=0.8 source=deduced -->
<!-- ndf: refines=CON-SLA-011 depends-on=DEC-060,DEC-062,BEH-021,BEH-022,BEH-023,CON-POC-001 -->

> **track: poc | status: draft** - 提案 `spec/open/proposal-io-pipelining.md`
> （r3：Buffered 主目标，对齐 [[DEC-062]]）。
> POC 阶段不纳入生产 SLA（[[CON-POC-001]]）。以下为 POC 验证目标，非 must 承诺。
> **v1 smoke（~24 QPS、无诚实 cgroup）不可信，MUST NOT 引用为 R0 或增量证据。**
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
| SIFT1M 1T QPS | ~2128–2450（诚实 cgroup） | ≥ R0 × 1.03 | L5 + L4 协作；逼近 hnswlib ~2800 |
| SIFT1M 4T QPS | ~5000–8312 | ≥ R0 × 1.02 | 多线程收益递减 |
| Recall@10 | ≥ 95% | ≥ 95% (不变) | 预取不改变候选集 |
| RSS 增量 | - | ≤ +1MB | pipe_ring_ buffer pool |

### 辅表：O_DIRECT（诚实地板 / 必然 I/O）

| 指标 | 基线 (O_DIRECT) | POC 目标 | 说明 |
|------|-----------------|----------|------|
| SIFT1M 1T QPS | 130 | ≥ 140 | L5 I/O 重叠 |
| SIFT1M 4T QPS | 502 | ≥ 540 | 多线程重叠效果递减 |
| DEEP10M 4T QPS | 169 | ≥ 220 | Phase A ~7ms 可隐藏大量 I/O |

### 证据状态（[[DEC-063]] / [[DEC-064]]，非 must）

| 场景 | 结论 | 口径 |
|------|------|------|
| SIFT1M R0–R4 Buffered | **负结果**（无收益） | 诚实 cgroup；见 [[DEC-063]] |
| DEEP10M 1T pre-memopt | 相对 +162.6%（pipe） | **Buffered+EVICT** 相对对比；**≠** 本辅表 O_DIRECT 达标 |
| DEEP10M post-memopt | pipe **无收益**（R1≈R0） | [[DEC-064]]；BEH-021 保持 draft |
| DEEP10M O_DIRECT 辅表 | **未验收** | 不得把 Buffered+EVICT 数字填入本表 |

> 若 POC 验证通过，promote 时分别评估是否抬升 [[CHR-006]] Buffered 与/或
> [[CON-SLA-011]] Honest 下限。负结果走 [[BEH-020]]。

## POC 不纳入生产 SLA {#CON-POC-001}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.7 source=deduced -->
<!-- ndf: refines=CHR-008 depends-on=BEH-018,ARCH-008 -->

`poc/` 与 draft 探索条款下的 QPS/Recall 数字 MUST NOT 自动成为 [[CHR-006]] /
[[CON-SLA-011]] 等 Trunk SLA 的一部分。相对对比实验若基线协议不同于诚实锚点，
MUST 在 DEC/提案中标注口径（同 [[DEC-061]]）。
