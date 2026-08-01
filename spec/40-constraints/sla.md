# Constraints — SLA / 诚实 I/O

> 条款索引: `CON-SLA-008`, `CON-SLA-009`, `CON-SLA-010`, `CON-HONEST-002`, `CON-SLA-011`, `CON-SLA-012`

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
