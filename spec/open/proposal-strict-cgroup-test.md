# Proposal: 严格 cgroup 内存隔离测试协议 {#PROP-STRICT-CGROUP-TEST}

> track: process
> Status: Implemented on 2026-08-03
> Amendment: 2026-08-03 — 方案 A：[[CON-SLA-014]] 升格 `status=stable`（Trunk 一等公民）；
> 验收 ID 由误用的 VER-035 更正为 [[VER-039]]（VER-035/038 已占用）。
> 日期: 2026-08-03
> 关联: [[CHR-001]], [[CHR-005]], [[CHR-006]], [[CON-HONEST-002]], [[CON-SLA-011]], [[CON-SLA-014]], [[DEC-059]], [[DEC-057]], [[DEC-062]], [[DEC-065]], [[VER-039]]
> 场景: 场景3（规范重构 / 审核闭环）

## 1. 动机

### 1.1 核心设计哲学

DiskHNSW 的设计意图是：**在受限内存的机器上尽可能多地获取性能，运行更大规模的图检索。**

page cache 是实现这一目标的核心合法加速层：

- cgroup 预算 = RSS + page cache（file），两者共享 `memory.max`
- RSS 越省（CSR 压缩、PQ 编码、VisitedList uint8 等优化），留给 page cache 的预算越多
- page cache 越多，vecblocks 命中率越高，检索越快
- 这是 DiskHNSW 相比 hnswlib（全内存）的核心价值--用更少的内存跑更大的图

**本提案不禁止 page cache。恰恰相反--保障 page cache 在 cgroup 预算内被充分利用。**

### 1.2 问题陈述

问题不是"有 page cache"，而是"有超出 cgroup 预算的 page cache"。

当前测试实践中，数据准备和检索在同一台机器上执行，导致 page cache 串台：

```
理想情况 (严格隔离, 模拟跨机器部署):
  cgroup 512MB = RSS 269MB + page cache 243MB
  → page cache 在预算内, 合法, 性能数据有效

白嫖情况 (当前问题, 同机数据准备+检索):
  cgroup 512MB = RSS 269MB + cgroup file ~50MB
  + root cgroup 白嫖的 ~450MB vecblocks cache
  → 实际用了 ~770MB, 但测试报告说"512MB 下 QPS 2300"
  → 数字虚高, 误导设计决策
```

**根因**：cgroup v2 page cache 记账规则为"首次读取者归属"。数据准备工具（pipeline）在 root cgroup 中运行并读取了数据文件，page cache 归属 root。benchmark 进程随后在子 cgroup 中读同一文件，页面已在 cache 中，不重新记账。这不是 bug，是 cgroup v2 的设计--但数据准备和检索是两个独立阶段（[[CHR-005]] 第 4 点："索引构建是离线 batch"），不应共享 cache 预算。

**影响**：

1. **SLA 验收数字失真**：[[CHR-006]] Buffered QPS ≥ 2000 可能在白嫖条件下完成验收
2. **设计约束被突破**：[[CHR-001]] "可用 page cache 预算 = limit − RSS" 在实际测试中不成立
3. **优化决策被误导**：[[DEC-059]] 的 page cache 覆盖率分析高估了实际可用量

### 1.3 真实部署场景

用户提出的真实场景：**数据准备在内存充足的机器上完成，文件拷贝到内存受限机器上进行检索。**

这是真实部署路径：
1. 数据准备在内存充足的机器上完成（无 cgroup 限制）
2. 产出文件拷贝到部署机器磁盘
3. 部署机器内存受限，启动检索进程
4. 部署机器上无预热的 page cache（文件刚拷贝，从未被读）
5. 检索进程首次读取文件，page cache 记账归属检索进程的 cgroup
6. **cgroup 记账准确，无白嫖**

**当前测试问题 = 在同一台机器上跑数据准备 + 检索，page cache 串台。**

### 1.4 drop_caches 如何模拟跨机器部署

drop_caches 不是在模拟"迁移"这个动作，而是在**重置 page cache 状态到等价于文件刚到达新机器的初始态**：

- 真实跨机器：文件拷贝到新机器 → 新机器从未读过这些文件 → page cache 为空
- 同机模拟：数据准备完成 → `drop_caches` 清空 page cache → 等价于"从未读过"

两种场景下 cache 状态完全一致。drop_caches 后 benchmark 首次读取文件，page cache 从零开始在 cgroup 内记账积累，RSS + page cache 总量受 `memory.max` 严格约束。

**page cache 不会消失，而是从零开始在预算内诚实积累。**

---

## 2. 提案

### 2.1 新增测试协议

新增 [[CON-SLA-014]]（严格 cgroup 隔离测试协议，**stable must / 一等公民**）和
[[VER-039]]（严格隔离验收），作为 [[CON-HONEST-002]] 的补充。所有 SLA 验收
benchmark MUST 在严格隔离条件下执行。

### 2.2 协议定义

**名称**：严格 cgroup 内存隔离测试协议（Strict Cgroup Isolation Protocol）

**设计意图**：保障 page cache 在 cgroup 预算内被充分利用。不禁止 page cache，而是确保不偷用预算外的内存。

**前置条件**：
1. 数据准备（pipeline 工具链）已完成，产出文件就绪
2. 数据准备和检索可在同一台机器上，但 MUST 执行 cache 清场

**清场操作**（推荐方法 A）：

| 方法 | 操作 | 模拟场景 | 说明 |
|------|------|----------|------|
| **A. drop_caches** | `sync && echo 3 > /proc/sys/vm/drop_caches` | 文件刚拷贝到部署机器 | 全局清空，简单可靠 |
| **B. posix_fadvise** | 对每个数据文件调用 `POSIX_FADV_DONTNEED` | 同上 | 只驱逐特定文件，需代码支持 |

**测试流程**：
```
1. [可选] 运行数据准备 pipeline（root cgroup，无限制）
2. 确认产出文件就绪（graph/bfs/blocks/route/vecblocks/PQ）
3. sync && echo 3 > /proc/sys/vm/drop_caches    # 清场
4. [可选] fincore/vmtouch 验证文件不在 cache 中
5. 创建 cgroup: mkdir /sys/fs/cgroup/hnsw_strict && echo <limit> > memory.max
6. 将 benchmark 进程加入 cgroup: echo <pid> > cgroup.procs
7. 启动 benchmark（所有 I/O 首次读取，page cache 在 cgroup 内记账积累）
8. 后台监控 memory.current / memory.stat（100ms 采样）
9. benchmark 结束，收集 memory.peak / memory.events / memory.stat
10. [可选] fincore 验证文件在 cache 中的实际页数
```

### 2.3 对照实验矩阵

| 实验组 | cgroup | drop_caches | 模拟场景 | 用途 |
|--------|--------|-------------|----------|------|
| **A: 无限制** | 无 | 否 | 无内存限制 | 上界参考 |
| **B: 限制未清场** | 512MB | 否 | 同机数据准备+检索 | 暴露白嫖程度（B vs C = 白嫖收益） |
| **C: 严格隔离** | 512MB | 是 | 跨机器部署（文件刚拷贝） | **SLA 验收唯一合法条件** |

- **C 组是 SLA 验收的唯一合法条件**
- C 组中 page cache 依然存在且发挥作用，只是被限制在 cgroup 预算内
- B 组仅用于对比分析（B vs C 差值 = 白嫖带来的性能虚高），不作为验收依据

### 2.4 监控指标

每个实验组 MUST 采集：

**cgroup 级（核心）**：

| 指标 | 来源 | 含义 |
|------|------|------|
| `memory.current` | cgroup | 总内存（anon + file），MUST ≤ memory.max |
| `memory.peak` | cgroup | 峰值内存 |
| `anon` | memory.stat | 匿名页（进程数据结构） |
| `file` | memory.stat | 本 cgroup 产生的 page cache |
| `active_file` | memory.stat | 活跃文件页（热数据） |
| `inactive_file` | memory.stat | 非活跃文件页（可回收） |
| `workingset_refault_file` | memory.stat | 文件页回收后再次访问（cache 抖动指标） |
| `pgmajfault` | memory.stat | major page fault（I/O 瓶颈指标） |
| `oom` | memory.events | OOM 事件计数（MUST = 0） |

**进程级（辅助）**：

| 指标 | 来源 | 含义 |
|------|------|------|
| VmRSS | /proc/self/status | 进程 RSS（不含 read page cache） |
| BlockCache hit% | benchmark 输出 | 进程内缓存命中率 |
| QPS / Recall | benchmark 输出 | 性能指标 |

**文件级（验证）**：

| 指标 | 工具 | 含义 |
|------|------|------|
| cached pages | `fincore` / `vmtouch` | 文件在 page cache 中的实际页数 |

### 2.5 预期影响

#### SIFT1M @ 512MB cgroup

| 指标 | B 组（白嫖） | C 组（严格） | 差异分析 |
|------|-------------|-------------|----------|
| RSS | ~269MB | ~269MB | 不变（匿名内存不受影响） |
| cgroup file | ~50MB | ~240MB+ | C 组 file 上升（vecblocks/graph/PQ 全部记账到 cgroup） |
| cgroup peak | ~320MB | ~500MB? | C 组逼近 512MB 限制 |
| QPS (Buffered) | ~2300 | ??? | C 组 page cache 限制在 ~240MB 内（512-269），B 组白嫖了 ~450MB。差值 = 白嫖收益 |
| QPS (O_DIRECT) | ~130 | ~130 | 不变（O_DIRECT 不用 page cache） |

如果 C 组 `memory.peak` 超过 512MB，说明 **512MB 在严格隔离下不足以运行 SIFT1M**。

#### DEEP10M @ 2GB cgroup

| 指标 | B 组（白嫖） | C 组（严格） | 差异分析 |
|------|-------------|-------------|----------|
| RSS | ~1612MB | ~1612MB | 不变 |
| cgroup file | ~100MB | ~390MB+ | vecblocks 3.7GB 不可能全装入，但热数据会进 cache |
| cgroup peak | ~1700MB | ~2000MB? | 逼近 2GB 限制 |
| QPS (Buffered) | ~2340 | ??? | 如果 workingset_refault 上升，QPS 可能下降 |

---

## 3. NDF 变更清单

### 3.1 新增条款

| 位置 | ID | 类型 | 内容 |
|------|-----|------|------|
| `40-constraints/sla.md` | `CON-SLA-014` | constraint, must, L1, **stable** | 严格 cgroup 隔离测试协议（一等公民） |
| `50-verification/acceptance-p2.md` | `VER-039` | verification, must, L1, stable | SLA 验收必须在严格隔离条件下执行（原误标 VER-035） |

### 3.2 修改条款

| 位置 | ID | 修改内容 |
|------|-----|----------|
| `00-charter/charter.md` | `CHR-006` | 验收条件追加"严格隔离"前置条件引用 |
| `40-constraints/sla.md` | `CON-HONEST-002` | 追加引用 [[CON-SLA-014]] |

### 3.3 新增决策

| 位置 | ID | 内容 |
|------|-----|------|
| `decisions/06-strict-cgroup.md` | `DEC-065` | 严格 cgroup 隔离测试协议确立 |

### 3.4 条款草案

#### CON-SLA-014

```markdown
## 严格 cgroup 隔离测试协议 {#CON-SLA-014}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.9 source=deduced -->
<!-- ndf: refines=CON-HONEST-002 depends-on=DEC-065 -->

> **一等公民**：Trunk SLA 验收强制前置；白嫖对照组 MUST NOT 作验收依据。

所有 SLA 验收 benchmark MUST 在严格 cgroup 隔离条件下执行。

**协议**：
1. benchmark 启动前 MUST 执行 `sync && echo 3 > /proc/sys/vm/drop_caches` 清空 page cache
2. benchmark 进程 MUST 运行在受限 cgroup 内（`memory.max` = SLA 规定值）
3. benchmark 启动后所有文件 I/O 为首次读取，page cache 在 cgroup 内记账积累
4. 测试过程中 MUST 监控 `memory.current`、`memory.peak`、`memory.stat`（anon/file）
5. `memory.events` 中 `oom` MUST = 0（不得触发 OOM）

**模拟场景**：此协议模拟真实部署--数据准备在内存充足机器上完成，
文件拷贝到内存受限机器上进行检索。部署机器上无预热的 page cache。
drop_caches 将 page cache 状态重置到等价于"文件刚到达"的初始态，
使 cgroup 记账准确。page cache 在预算内合法积累，不被消灭。

**白嫖对照组**：允许额外运行"未清场"组用于对比分析，但其结果
MUST NOT 作为 SLA 验收依据。

> rationale: cgroup v2 page cache 记账规则为"首次读取者归属"。
> 当数据准备（root cgroup）和检索（子 cgroup）在同一台机器上执行时，
> 数据准备阶段预热的 page cache 不会被重新记账到 benchmark cgroup，
> 导致 benchmark 实际可用内存远超 cgroup 限制，性能数字虚高。
> drop_caches 清场模拟了跨机器部署场景，确保 cgroup 记账准确。
> page cache 在 cgroup 预算内（limit - RSS）是核心合法加速层，本协议保障其在预算内被诚实利用。
```

#### VER-039（原误标 VER-035；035/038 已占用）

```markdown
## 严格隔离验收 {#VER-039}
<!-- ndf: kind=verification level=must layer=L1 status=stable since=0.9 source=deduced -->
<!-- ndf: verifies=CON-SLA-014,CHR-006,CON-SLA-011 depends-on=DEC-065 -->

[[CHR-006]] 和 [[CON-SLA-011]] 中的所有 QPS/Recall/RSS 指标 MUST 在
[[CON-SLA-014]] 严格 cgroup 隔离条件下验证（或重新验证）。

验收报告 MUST 包含：
1. cgroup `memory.peak`（证明总内存未超限）
2. cgroup `memory.stat` 中的 `anon` 和 `file` 分项（证明 page cache 在预算内）
3. `memory.events` 中的 `oom` 计数（证明未触发 OOM）
4. [可选] `fincore`/`vmtouch` 文件缓存验证

> rationale: 现有 SLA 数字可能是在 page cache 白嫖条件下测得的，
> 需在严格隔离条件下验证以确保数字诚实性。
```

#### DEC-065

```markdown
## D-065: 严格 cgroup 隔离测试协议确立 {#DEC-065}
<!-- ndf: kind=decision date=2026-08-03 affects=CON-HONEST-002,CHR-006,CON-SLA-011,CON-SLA-014,VER-039 source=deduced -->

**Context.** [[CON-HONEST-002]] 和 [[CHR-001]] 规定 page cache 与 RSS 共享
cgroup 预算。但实际测试中，数据准备（root cgroup）预热的 page cache 不会被
重新记账到 benchmark cgroup（cgroup v2 "首次读取者归属"规则），导致 benchmark
白嫖 root 预热的 cache，实际可用内存远超 cgroup 限制。

真实部署场景中，数据准备在内存充足机器上完成，文件拷贝到内存受限机器上检索。
部署机器上无预热的 page cache，cgroup 记账天然准确。

**Decision.** 确立严格 cgroup 隔离测试协议（[[CON-SLA-014]]）为 Trunk 一等公民
（stable must）：
- benchmark 前 `drop_caches` 清空 page cache，模拟跨机器部署
- benchmark 在 cgroup 内首次读取文件，page cache 在预算内诚实积累
- 所有 SLA 验收 MUST 在此条件下执行（[[VER-039]]）

page cache 在 cgroup 预算内（limit - RSS）是核心合法加速层。本协议不禁止
page cache，而是保障其在预算内被诚实利用，消除测试中偷用物理机其他空闲
内存导致的性能误差。

**Alternatives rejected.**
- 禁止 page cache（O_DIRECT only）：违反 [[DEC-062]] Buffered 为生产主目标
- 跨机器部署测试：成本高，drop_caches 在同机上等价模拟
- 修改 cgroup 记账规则：不可能，cgroup v2 设计如此
- 长期 draft CON-SLA-014：否决（stable 不得依赖 draft）
```

---

## 4. 实施计划

### 4.1 工具准备

```bash
sudo apt install -y linux-tools-common linux-tools-$(uname -r)  # fincore
# 或
sudo apt install -y vmtouch
```

### 4.2 SIFT1M 对照实验

3 组对照（A/B/C），~5 分钟/组。
- 核心目标：C 组 `memory.peak` 是否超 512MB，QPS 是否下降
- C ≈ B：说明有效热区远小于 vecblocks 总量，现有 SLA 数字有效
- C < B：说明白嫖的 cache 在贡献性能，需更新 SLA 数字

### 4.3 DEEP10M 对照实验

3 组对照，~30 分钟/组。
- 核心目标：2GB cgroup 在严格隔离下是否可行

### 4.4 结果处理

- C 组数字 ≈ B 组：只追加测试协议条款，不修改 SLA 数字
- C 组数字明显恶化：修改 [[CHR-006]] / [[CON-SLA-011]] SLA 数字，或上调 cgroup 限制

---

## 5. 开放问题

| # | 问题 | 待定 |
|---|------|------|
| Q-001 | 512MB cgroup 严格隔离下是否足够运行 SIFT1M？ | 阶段 4.2 回答 |
| Q-002 | 2GB cgroup 严格隔离下是否足够运行 DEEP10M？ | 阶段 4.3 回答 |
| Q-003 | C 组 QPS 下降时，是 cache 抖动还是 I/O 延迟？ | workingset_refault / pgmajfault 数据回答 |

---

## 6. 非目标

- 不修改数据准备 pipeline 的 cgroup 归属
- 不修改 benchmark 代码的 I/O 模式（O_DIRECT / Buffered 双轨不变）
- 不改变 Buffered 为生产优化主目标的定位（[[DEC-062]]）
- 不改变 O_DIRECT 为诚实验收地板的定位（[[DEC-059]]）
- **不禁止或贬低 page cache 的作用**--page cache 在 cgroup 预算内是核心合法加速层
- 本提案只定义测试协议（确保记账准确），不定义新的优化方向
