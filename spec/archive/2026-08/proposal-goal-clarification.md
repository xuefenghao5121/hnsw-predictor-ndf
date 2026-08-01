# Proposal: 项目目标澄清与多层内存优化策略重定位

> track: process
> 关联: [[CHR-001]]、[[CHR-004]]、[[CHR-006]]、[[DEC-059]]、[[DEC-060]]、[[DEC-062]]、[[BEH-021]]、[[BEH-022]]、[[BEH-023]]、[[CON-HONEST-002]]
> 日期: 2026-08-01
> Status: **Implemented on 2026-08-01** — 闭合见 `spec/open/proposal-buffered-primary-plan-a.md` + [[DEC-062]]
> 归档: `spec/archive/2026-08/`（原误放 `spec/open/archive/`）

## 1. 问题陈述

I/O Pipelining POC 实现过程中暴露了对项目目标的理解偏差：

1. **误将 O_DIRECT 当作主优化目标**：提案 r2 虽然写了"统一多层架构"，但实际 benchmark 和分析仍以 O_DIRECT 为主，Buffered 被当作"page cache 已足够、不需要优化"的附属
2. **误将 page cache 视为"白嫖"**：实际上 page cache 在 cgroup 预算内是合法资源，是生产环境的核心加速层
3. **偏离项目核心目标**：项目目标是**在有限内存下逼近 hnswlib 全内存方案性能**，不是仅优化磁盘 I/O 地板

## 2. 项目目标重申

### 2.1 核心目标 (对齐 [[CHR-001]])

在诚实的 cgroup 内存限额下（SIFT1M: 512MB），利用磁盘驻留向量数据，**逼近 hnswlib 全内存方案的检索性能**。

- **hnswlib 全内存基线**: SIFT1M 1T ~2800 QPS / 4T ~5800 QPS / RSS ~726MB
- **当前 DiskHNSW Buffered**: 1T ~2128 QPS / 4T ~5000 QPS / RSS ~269MB (512MB cgroup)
- **差距**: 1T 差 24%，4T 差 14%
- **目标**: 缩小差距，在 2.5x 内存节省的前提下逼近全内存性能

### 2.2 "诚实内存"的含义 (对齐 [[DEC-059]]、[[CON-HONEST-002]])

- cgroup v2 `memory.max` 同时约束匿名内存和 page cache
- page cache 可用量 = `memory.max - RSS`，是**有限的合法资源**
- page cache **不是无限制白嫖系统内存**，但在预算内使用完全正当
- Buffered 模式利用 page cache 是**生产推荐路径**，不是投机取巧

### 2.3 两种模式的定位修正

| | 之前的理解（错误） | 修正后 |
|--|------------------|--------|
| **Buffered** | "page cache 帮忙，不用优化" | **生产主目标，优化主战场** |
| **O_DIRECT** | "诚实地板，优化第一优先级" | **诊断基座 + 必然磁盘 I/O 的优化路径** |
| **关系** | O_DIRECT 优化成果会自然惠及 Buffered | 两者各有优化空间，不假设线性传递 |

**O_DIRECT 仍然有价值**：生产中一定有磁盘 I/O 发生（page cache miss），这些 I/O 的效率需要 O_DIRECT 路径优化。但 O_DIRECT 不是唯一的、甚至不是主要的优化目标。

## 3. 多层内存优化策略 (修订)

### 3.1 目标函数

在 cgroup 内存预算内，最大化 QPS：

```
QPS_total = QPS_compute + QPS_L4cache + QPS_L5pipe + QPS_disk

优化方向:
  - L1/L2/L3: 减少 CPU 计算延迟 (_mm_prefetch, SIMD)
  - L4 (page cache): 提高命中率 (预算管理 + 预热策略)
  - L5 (pipe_ring_): 重叠 I/O 与 CPU (Phase A 期间预取)
  - Disk: 减少 I/O 需求 (PQ 精度 → 更少候选)
```

### 3.2 各层优化定位

#### L4: Page Cache — Buffered 模式的核心加速层

| 属性 | 说明 |
|------|------|
| 容量 | `cgroup_limit - RSS`（SIFT1M: ~240MB, DEEP10M: ~390MB） |
| 角色 | **Buffered 模式的主要性能来源**，不是附属 |
| 优化方向 | 1. 提高有效页的驻留率（减少冷页污染）<br>2. 管理预算：`posix_fadvise(DONTNEED)` 主动驱逐冷页<br>3. pipe_ring_ 的 Buffered I/O 自然填充 L4 |

**关键认知**：当前 Buffered 2128 QPS vs hnswlib ~2800 QPS 的差距，部分原因是 L4 的 240MB 预算只能覆盖 vecblocks 496MB 的 ~48%。提高有效覆盖率（而非绕过 L4）是 Buffered 优化的核心方向。

#### L5: pipe_ring_ — I/O 与 CPU 重叠的主动机制

| 属性 | 说明 |
|------|------|
| 角色 | Phase A 期间异步预取 Fine Rerank 候选页 |
| Buffered 模式价值 | 1. 填充 L4（Buffered I/O 自然入 page cache）<br>2. 对 page cache miss 的页提前发起 I/O<br>3. 减少 Phase B 的串行等待 |
| O_DIRECT 模式价值 | 唯一的 I/O 重叠机制（O_DIRECT 不经 L4） |

**修正**：pipe_ring_ 不是"主要给 O_DIRECT 用的"，两种模式都有价值。Buffered 模式下 pipe_ring_ 的价值在于**主动管理 L4 预算** — 把即将需要的页提前拉入有限的 page cache。

#### L1/L2/L3: CPU Cache — 计算加速

| 属性 | 说明 |
|------|------|
| 角色 | 减少距离计算的内存访问延迟 |
| 当前效果 | SIFT1M 实测无收益（Phase A ~0.5ms, 计算占比小） |
| 潜在场景 | DEEP10M PQ 计算密集时，或减少候选数后计算占比上升 |

## 4. 拟修订条款

### {#CHR-001} 修订 (L0, stable)

在 [[CHR-001]] 现有内容后追加澄清段落：

> **优化主目标**：Buffered 模式（生产默认）是性能优化的主要目标。目标是在诚实 cgroup
> 预算下逼近 hnswlib 全内存方案性能。page cache 在预算内是合法的核心加速层。
> O_DIRECT 模式是诚实验收地板和必然磁盘 I/O 的优化路径，两者各有独立优化空间。

### {#BEH-021} 修订 (draft)

在现有 I/O Pipelining 行为条款基础上，明确 Buffered 模式的核心价值：

> **Buffered 模式下 pipe_ring_ 的核心价值**：主动填充 L4 (page cache)，而非仅"绕过 L4"。
> pipe_ring_ 的 Buffered I/O 读取将即将需要的候选页提前拉入有限的 page cache 预算，
> 减少 Phase B 中 page cache miss 导致的磁盘 I/O 等待。

### {#CHR-004} 修订 (draft)

P3 阶段描述修正：

> P3（进行中）：多层内存优化 + 大规模验证。Buffered 模式逼近 hnswlib 性能为主要目标；
> O_DIRECT 地板优化为辅助路径。多层策略：L4 page cache 预算管理 + L5 pipe_ring_ I/O 重叠 +
> L1/L2/L3 CPU cache 计算加速。

## 5. 不做的事

- 不放弃 O_DIRECT 优化（必然磁盘 I/O 仍需优化）
- 不改变 cgroup 诚实协议（[[CON-HONEST-002]] 不变）
- 不修改 stable SLA 数字（[[CHR-006]]、[[CON-SLA-011]] 不变）
- 不修改 NDF poc track 已落地的 draft 条款状态

## 6. 后续影响

- I/O Pipelining POC (proposal-io-pipelining.md) 的优化重点从"O_DIRECT 为主"调整为"Buffered 为主"
- Benchmark 设计：R0-R4 以 Buffered 为核心对比组，O_DIRECT 为辅助验证组
- 未来优化方向新增：L4 page cache 预算管理（`posix_fadvise` 主动驱逐冷页、提高有效覆盖率）

## 7. POC 纪律补充

**每次 POC 优化前 MUST 先对齐基线**：

1. 在与优化目标一致的配置（cgroup、线程数、数据集、模式）下先跑基线
2. 基线数字 MUST 记录到 POC NOTES 中作为 R0 锚点
3. 后续每轮优化 MUST 与 R0 对比，不得跳过基线直接对比
4. 若基线与 NDF SLA（[[CHR-006]] / [[CON-SLA-011]]）偏差超过 10%，MUST 先定位根因再继续优化

> rationale: POC 优化如果基线不对齐，所有增量数字都是无意义的。之前 Buffered 模式
> 因 FINE_PREAD 配置错误和 cgroup 未生效导致基线失真，浪费了多轮 benchmark 时间。
