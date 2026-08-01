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
<!-- ndf: refines=DEC-039,DEC-059 depends-on=DEC-057 -->

性能基准测试 MUST 至少报告两组数据：
1. **Buffered**: `FINE_BUFFERED=1`（含 page cache）
2. **Direct**: `FINE_DIRECT=1`（O_DIRECT，无 page cache）

两组模式 MUST 在同一 cgroup 限制下运行。Buffered 模式下，page cache 计入
cgroup 内存使用，运行过程中峰值内存（anon + file）MUST NOT 超过 cgroup 限制。

**cgroup 预算约束（[[DEC-059]] 确立）**：page cache 与匿名内存共享 cgroup `memory.max`
预算。可用 page cache 预算 = `memory.max - RSS`。在运行过程中加载的 page cache
不得使总内存（anon + file）超过限制，否则触发 OOM kill 或 memory reclaim。
随数据规模增大，page cache 对 vecblocks 的覆盖率趋近于 0：

| 规模 | cgroup | RSS | 可用 page cache | vecblocks | 覆盖率 |
|------|--------|-----|----------------|-----------|-------|
| SIFT1M | 512MB | 269MB | ~240MB | 496MB | ~48% |
| DEEP10M | 2GB | 1612MB | ~390MB | 3.7GB | ~10% |
| 100M (预估) | 4GB | ~2GB | ~2GB | ~50GB | ~4% |

因此 O_DIRECT 路径（性能地板）是优化的第一优先级，page cache 是在剩余预算内
的有限加速手段（[[DEC-059]]）。抬高地板的工程路线图见 [[DEC-060]]（非本条款 SLA）。

报告 MUST 标注测量模式。仅报告 Buffered 模式数字时 MUST 附带声明：
"此数字在 cgroup 限制内运行，page cache 与匿名内存共享内存预算"。

> rationale: cgroup v2 的 memory.max 同时限制匿名内存和 page cache。Page cache
> 不是免费资源——它与 RSS 竞争同一块预算。Buffered 模式是生产推荐路径，
> page cache 是 OS 在剩余预算内自动管理的冷热分层，但可用量受限。
> O_DIRECT 模式消除 page cache 后，测量的是纯匿名内存 + 真实磁盘 I/O 的性能，
> 代表无缓存时的性能地板，是 I/O 优化的基座。
> 关联决策: [[DEC-059]]（战略重新校准）、[[DEC-060]]（I/O 优化方案）

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
<!-- ndf: refines=CON-SLA-011 depends-on=DEC-060,BEH-021,BEH-022,BEH-023,CON-POC-001 -->

> **track: poc | status: draft** - 提案 `spec/open/proposal-io-pipelining.md`（2026-08-01, r2 统一多层架构）。
> POC 阶段不纳入生产 SLA（[[CON-POC-001]]）。以下为 POC 验证目标，非 must 承诺。
>
> 分层验证目标 (R0-R4 逐层叠加):
>
> | 轮次 | 配置 | 验证目标 |
> |------|------|----------|
> | R0 | 基线 (PIPE_FINE=0) | 锚定基线 QPS/Recall/RSS |
> | R1 | + L5 only (PIPE_FINE=1) | pipe_ring_ I/O 重叠的独立贡献 |
> | R2 | + L5 + L1 (PIPE_FINE=1, PIPE_L1=1) | CPU cache 预取的增量 |
> | R3 | + L5 + L4 (PIPE_FINE=1, PIPE_L4=1) | L4 旁路填充的跨 query 效果 |
> | R4 | + L5 + L4 + L1 (全开) | 叠加上限 |

| 指标 | 基线 (O_DIRECT) | POC 目标 | 说明 |
|------|-----------------|----------|------|
| SIFT1M 1T QPS | 130 | ≥ 140 | L5 I/O 重叠 |
| SIFT1M 4T QPS | 502 | ≥ 540 | 多线程重叠效果递减 |
| DEEP10M 4T QPS | 169 | ≥ 220 | Phase A ~7ms 可隐藏大量 I/O |
| Recall@10 | ≥ 95% | ≥ 95% (不变) | 预取不改变候选集 |
| RSS 增量 | - | ≤ +1MB | pipe_ring_ buffer pool (thread_local) |

> 若 POC 验证通过，promote 提案将更新 [[CON-SLA-011]] 的 Honest 下限。
> 若 POC 负结果，走 [[BEH-020]] 负结果闭环。

## POC 不纳入生产 SLA {#CON-POC-001}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.7 source=deduced -->
<!-- ndf: refines=CHR-008 depends-on=BEH-018,ARCH-008 -->

`poc/` 与 draft 探索条款下的 QPS/Recall 数字 MUST NOT 自动成为 [[CHR-006]] /
[[CON-SLA-011]] 等 Trunk SLA 的一部分。相对对比实验若基线协议不同于诚实锚点，
MUST 在 DEC/提案中标注口径（同 [[DEC-061]]）。
