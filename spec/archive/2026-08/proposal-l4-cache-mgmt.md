# Proposal: L4 Page Cache 主动管理 - 避免内核盲目回收 {#PROP-L4-CACHE-MGMT}

> track: poc
> Status: Implemented on 2026-08-03
> 日期: 2026-08-03
> 修订: r2 — 审查收口：Pending；[[BEH-024]]；禁止 EVICT 幽灵；统一预算；改写 file 目标
> 关联: [[CHR-001]], [[CHR-006]], [[CON-SLA-014]], [[DEC-059]], [[DEC-066]], [[BEH-021]], [[BEH-023]], [[BEH-024]]
> 相关并行: `proposal-io-behavior-correction.md`（pipe_ring_）；**本 POC 优先**（先稳 L4 再叠 L5）
> 基线: SIFT1M 严格隔离 ([[DEC-066]]) Buffered 1T=22.9 QPS
> 主题装订器: `poc/l4-cache-mgmt/ndf/TOPIC.md`（[[BEH-025]]）

## 1. 动机

### 1.1 问题现象

严格隔离（[[CON-SLA-014]]）下 Buffered 1T 仅 22.9 QPS（vs 白嫖 era ~2300）：

| 指标 | 值 |
|------|-----|
| memory.peak | 512MB（满） |
| `max` events | 1523 |
| peak anon | 246MB |
| peak file | 400MB |
| Peak RSS 1T | **235MB**（对齐预算用此值） |

**预算公式（统一）**：`page_cache_budget ≈ memory.max − Peak_RSS`  
1T：512 − 235 = **277MB**；4T：512 − 416 = **96MB**。  
peak file=400MB ≫ 277MB → 内核 reclaim（`max` 事件暴涨）。  
（peak anon 与 Peak RSS 不同源，**不以 anon 替代 RSS 算预算**。）

### 1.2 为何 file 胀到 400MB

vecblocks 走 buffered `pread`，块进入 page cache；OS LRU **不知** HNSW 热/冷。  
另：`memory.stat` 的 `file` **含 graph/PQ 等全部文件页**，不只 vecblocks——成功标准不得写死「总 file≤277」。

### 1.3 RSS 构成（1T）

| 组成 | 大小 | 生命周期 |
|------|------|----------|
| upper / CSR / BlockCache / PQ / route / meta / flat | 逻辑合计 ~189MB | 静态（与 Init RSS 147 有分配/trim 差，不强制加总相等） |
| VisitedList 等 | ~40–48MB+ | 每查询 |
| **Init RSS** | **147MB** | |
| **Peak RSS 1T / 4T** | **235 / 416MB** | |

### 1.4 洞察

277MB（1T）理论上够热区，但需**主动**管 L4，而非 OS 盲目 LRU。  
GP 预取在白嫖 era 无感；L4 受控后可能重新有价值。  
与 [[BEH-023]]（`PIPE_L4` 旁路**填充**）互补：本方向是**驱逐/保留** → [[BEH-024]]。

---

## 2. 探索机制（`poc/l4-cache-mgmt/` only）

| 机制 | 描述 | 旋钮 |
|------|------|------|
| **A. 精准 DONTNEED** | Fine 读完后对非热 vecblocks 页 `posix_fadvise(DONTNEED)` | 新 POC env（如 `L4_DONTNEED=1`） |
| **B. WILLNEED** | 对热 block `posix_fadvise(WILLNEED)` | `L4_WILLNEED=1` |
| **C. L3/L4 分层** | BlockCache miss 时 `mincore` 探 L4；命中则普通 `pread`（**仍拷贝**，非零拷贝） | 后续 |
| **D. 选择性页面驱逐** | 基于现有真旋钮 **`FINE_FADVISE`**（或 POC 新旋钮）做选择性保留；**禁止**把 `EVICT_PAGE_CACHE` 当有效实现（幽灵/no-op，见 io-behavior 提案） | `FINE_FADVISE` / `L4_SELECTIVE=1` |

**优先级**：A → D（基于 FINE_FADVISE）→ B → C。

### 2.1 验证目标（探索，非 Trunk must）

| 指标 | R0 基线 | POC 目标 | 说明 |
|------|---------|----------|------|
| Buffered 1T QPS | 22.9 | ≥ R0 × 1.5（aspirational） | 同协议相对量 |
| `max` events | 1523 | 明显下降（目标 &lt;500 作参考） | |
| vecblocks 相关驻留/回收 | — | **主监控**（fincore/分文件或自建计数） | 不以总 `file`≤277 为硬成功 |
| peak file（总分） | 400MB | 报告即可；能降则佳 | 含非 vecblocks |
| Recall@10 | ≥95% | ≥95% | must 门槛不变 |
| RSS 1T | ≤300 | ≤300 | [[CHR-006]] |

### 2.2 协议

- 每组前 `drop_caches` + 512MB cgroup（[[CON-SLA-014]]）
- R0 须**复跑**确认 ~22.9 可复现后再比 R1+
- R0（无 L4 管理）vs R1(A) vs R2(A+B) vs R3(A+B+D)
- 采集：memory.stat + QPS/Recall/RSS + 尽量分文件 cache 指标

---

## 3. NDF 变更清单

| 位置 | ID | 动作 |
|------|-----|------|
| `20-behavior/search.md` | [[BEH-024]] | draft；旋钮/预算/depends-on 以本提案 r2 为准 |
| `open/` | 本提案 | Pending，待确认后 Implemented |
| `poc/l4-cache-mgmt/NOTES.md` | — | 2026-08-03 已与本提案对齐（禁 EVICT 幽灵；A–D 同表） |
| `30-interfaces/env.md` | API-011（可选） | **确认后再**加协议级 draft env |

**不**把相对 QPS 写入 stable must（[[CON-POC-001]]）。  
**不**声称本 POC「验证 [[BEH-023]]」——023 仍属 pipe/`PIPE_L4` 轨。

---

## 4. 非目标

- 不改 Trunk `src/`；不恢复白嫖 2300
- 不实现/复活幽灵 `EVICT_PAGE_CACHE` 文档语义当真功能
- 不把总 `file≤预算` 当作唯一成功门闩
- pipe_ring_ 完整重测见并行提案；本 POC 优先稳住 L4

---

## 5. 开放问题

| # | 问题 |
|---|------|
| Q-001 | 277MB 能盖住多少热 vecblocks？ |
| Q-002 | 4T 仅 ~96MB 预算时 A/D 是否仍有净收益？ |
| Q-003 | DONTNEED 开销是否吃掉命中收益？ |
| Q-004 | graph/PQ 的 file 占比多大——是否也要管？ |
