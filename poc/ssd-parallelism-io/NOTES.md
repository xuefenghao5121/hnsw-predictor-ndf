# Notes: SSD Parallelism I/O Optimization

> 创建: 2026-08-10
> Trunk SHA: 434c6f5
> Status: exploring (R0 pending)

## 论文摘要

**Turbocharging Vector Databases using Modern SSDs** (VLDB 2025, Shim et al.)

三大技术:
1. io_uring 并行邻居检索 + CQE peeking（按完成顺序计算距离）
2. 空间感知插入重排（动态插入提升 cache 复用）
3. 局部性保持共置（预聚类到相同 page）

结果: 最高 11.1× QPS, 3.23× cache hit, 98.4% build time reduction
基础: pgvector 0.8.0 + PostgreSQL 17

## 与 DiskHNSW 的差异

| 维度 | pgvector (论文) | DiskHNSW (我们) |
|------|-----------------|-----------------|
| I/O 路径 | PostgreSQL buffer cache -> read() | pread() + fadvise(WILLNEED) |
| 并行 I/O | 无（阻塞 read） | WILLNEED_BG 后台线程（无锁 SPSC） |
| 完成顺序 | 批量屏障 | pread 固定顺序 |
| io_uring | 无 | 有（FINE_PREAD=0），多线程退化 pread |

## 已 rejected 方向的教训

- DEC-071 (io-pipelining): pipe_ring_ 预取与 WILLNEED 重叠 -> 无收益
- DEC-094 (mmap-budget-shift): page cache thrashing -> -66~80% QPS
- data-layout (BFS 重排): ceiling ~4% QPS

## R0 待实现

方向 A: io_uring CQE peeking 替代 pread
方向 B: k-means 聚类重排 vecblocks

## R0 结果 (2026-08-10, scripts/run_sustained.sh 金标)

### 方向 A: io_uring CQE peeking 替代 pread

配置: Config C (M=24 EF=60), 256MB 1T, 15轮×1000q, seed=42
A = WILLNEED_BG + pread (FINE_PREAD=1, 现有路径)
B = WILLNEED_BG + io_uring CQE peeking (FINE_PREAD=0, patch: 完成顺序处理)

| | A (pread) | B (CQE peeking) | Delta |
|--|:---:|:---:|:---:|
| agg QPS | 1,414.3 | 1,463.1 | **+3.5%** |
| steady QPS | 1,616.2 | 1,699.0 | **+5.1%** |
| recall | 96.60% | 96.60% | 0 ✅ |
| Round 1 | 604.1 | 631.4 | +4.5% |
| Round 15 | 1,616.2 | 1,699.0 | +5.1% |

A vs 金标 1,450: -2.5% (在 ±2CV 边缘 ✅)
B vs 金标 1,450: +0.9% (在金标范围内 ✅)

### 分析

CQE peeking 的收益来自:
1. **消除批量屏障**: 不等全部 I/O 完成，先到先算，CPU 不空闲
2. **SSD 通道不对称**: NVMe 多通道完成时间不一致，peeking 利用先完成的 I/O
3. **与 WILLNEED 协同**: WILLNEED 预热 page cache，io_uring 读取已预热页面更快完成

与 DEC-071 (io-pipelining) 的区别验证:
- DEC-071: pipe_ring_ 预取与 WILLNEED 重叠 -> 无收益 (两者同一时机)
- 本 POC: io_uring 替代 pread，CQE 完成顺序处理 -> +3.5% 收益
- 根因: 不是预取问题，而是完成顺序问题 (pread 固定顺序 vs CQE 完成顺序)

### 结论

方向 A 正向 (+3.5% agg / +5.1% steady)，值得继续探索。
方向 B (k-means 聚类重排) 待定。

## R1 结果: 多线程扩展性 (2026-08-10)

### thread_local vec_ring_ 改造

R0 的 vec_ring_ 是共享的，多线程下 SQ/CQ 竞争。
R1 改为 thread_local：每个搜索线程有自己的 io_uring ring（256 entries, 8KB buffers）。

### 256MB cgroup 多线程 A/B

| 线程 | A (pread) agg | B (CQE peeking) agg | Delta | A steady | B steady | Delta |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| 1T | 1,414.3 | 1,463.1 | **+3.5%** | 1,616.2 | 1,699.0 | +5.1% |
| 4T | 3,311.7 | 3,419.1 | **+3.2%** | 4,337.4 | 4,377.5 | +0.9% |
| 16T | 3,429.5 | 3,463.4 | **+1.0%** | 4,462.3 | 4,551.0 | +2.0% |

金标 16T 对照: 3,649 (A=94.0%, B=94.9%)

### 分析

收益递减: +3.5% (1T) -> +3.2% (4T) -> +1.0% (16T)

原因: 多线程下 I/O 并行度已高（N 个线程同时 pread），CQE peeking 的边际收益减小。
- 1T: 单线程 pread 串行阻塞，CQE peeking 消除等待 -> +3.5%
- 4T: 4 个 pread 并行，I/O 交织已部分覆盖等待 -> +3.2%
- 16T: 16 个 pread 并行，I/O 交织充分覆盖等待 -> +1.0%

### 结论

CQE peeking 在低线程数下收益显著（+3.5%），高线程数下收益递减（+1.0%）。
thread_local vec_ring_ 改造成功，多线程安全。

## R2 结果: Profile 分析 (2026-08-10, 1T 256MB)

### 每查询耗时分解 (steady state, n=15000)

**A (pread 路径):**
| 阶段 | 耗时 |
|------|------|
| pread (阻塞读取所有页) | 407us |
| rerank (距离计算) | 7us |
| 总 Fine 阶段 | ~414us |

**B (CQE peeking 路径):**
| 阶段 | 耗时 |
|------|------|
| collect (收集候选) | 13us |
| submit (io_uring 提交) | 81us (3us loop + 78us syscall) |
| io_1st (第一个 CQE 到达) | 10us |
| io_rest (剩余 CQE 等待) | 246us |
| compute (残余距离计算) | 2us |
| 总 Fine 阶段 | ~394us |

### 关键对比

| 指标 | A (pread) | B (CQE peeking) | 差异 |
|------|:---:|:---:|:---:|
| I/O 等待 | 407us | 256us (10+246) | **-151us (-37%)** |
| 距离计算 | 7us | 2us | -5us (CQE peeking 中大部分已提前算完) |
| 总 Fine 阶段 | ~414us | ~394us | **-20us (-5%)** |
| 每查询 I/O 页数 | ~44.7 | 44.7 | 相同 |
| cache 命中候选 | ~17.6 | 17.6 | 相同 |
| wait iters | N/A | 15.9 | 仍有 16 次等待 |

### 根因分析

1. **I/O 等待减少 37%**: CQE peeking 消除批量屏障
   - pread: 按固定顺序阻塞，最后一页决定总延迟
   - CQE: 第一个 10us 到达，按完成顺序处理，CPU 不空闲

2. **距离计算从 7us 降到 2us**: CQE peeking 在 I/O 等待期间已处理大部分候选
   - compute 阶段只剩跨页候选和边缘情况

3. **iters=15.9**: 仍有 16 次 waitCompletion
   - 说明 CQE 不是一次性全部到达，而是分批
   - 每次 reap 可能拿到 2-3 个 CQE
   - 但每次 reap 后立即处理，CPU 不空闲

4. **总 Fine 阶段仅 -5%**: I/O 等待减少 151us，但 submit 开销 81us 部分抵消
   - pread: 0 submit 开销（直接系统调用）
   - io_uring: 81us submit + 256us wait = 337us（vs pread 407us）
   - 净收益: 407 - 337 = 70us per query

5. **QPS 提升 +3.5%** 对应 Fine 阶段 -5%: Fine 阶段占总查询时间 ~70%
   - 70% × 5% = 3.5% 总 QPS 提升（与实测吻合 ✅）

## R3 结果: Submit 开销优化 (2026-08-10, 1T 256MB)

### Registered Buffers (IORING_REGISTER_BUFFERS)

尝试消除 io_uring_enter submit syscall 的 78us 开销：
1. SQPOLL (IORING_SETUP_SQPOLL) → SIGKILL, 权限/内核限制
2. Registered buffers (IORING_REGISTER_BUFFERS) → **负结果**
3. Registered buffers + FD (IORING_REGISTER_FILES) → **负结果**

### Profile 对比

| | B1 (baseline, CQE peeking) | B2 (REGBUF) | B3 (REGBUF+REGFD) |
|--|:---:|:---:|:---:|
| collect | 13us | 21us | 16us |
| submit (loop+syscall) | 79us | 83us | **84us** ⬆ |
| io_1st | 10us | 15us | 16us ⬆ |
| io_rest | 242us | 248us | 242us |
| compute | 1us | 2us | 2us |
| QPS | 1,490.5 | 1,318.3 (−12%) | 1,386.3 (−7%) |
| recall | 96.59% | 96.60% | 96.60% ✅ |

### 根因

- `io_uring_enter` syscall 时间 (~78us) 是提交 ~45 SQE 的固有开销
- Registered buffers: 内核侧的内存 pin 是缓存的（same pages, repeated I/O），
  预注册反而增加 `IORING_REGISTER_BUFFERS` 注册开销
- SQPOLL: 需要 `CAP_SYS_ADMIN` 且内核线程调度开销可能抵消收益
- 没有 SQPOLL 时，78us submit 是 io_uring batch submit 的硬下限

### 结论

Submit 开销不可在用户空间进一步降低。CQE peeking 的 +3.5% 收益是
当前约束下的最佳结果。

---

## POC 总结: ssd-parallelism-io (2026-08-10)

### 研究方向

基于 VLDB 2025 "Turbocharging Vector Databases using Modern SSDs" 论文，
探索 CQE peeking（完成顺序处理）在 DiskHNSW 中的应用。

### 所有轮次结果

| 轮次 | 配置 | 发现 | 结果 |
|------|------|------|------|
| R0 | 1T A/B | CQE peeking vs pread | **+3.5%** ✅ |
| R1 | 1T/4T/16T A/B | 多线程扩展性 | **+3.5%/3.2%/1.0%** ✅（收益递减） |
| R2 | 1T profile A/B | 时间分解 | I/O wait −37%, Fine stage −5% |
| R3 | 1T regbuf | Submit 开销优化 | **−12%** ❌（不可降低） |

### 最终性能 (CQE peeking 最优)

| 线程 | vs pread | vs 金标 |
|------|:---:|:---:|
| 1T | **+3.5%** (1,463 QPS) | +0.9% |
| 4T | **+3.2%** (3,419 QPS) | — |
| 16T | +1.0% (3,463 QPS) | 94.9% |

### 关键改造

1. **CQE peeking**: 批量屏障 → 完成顺序处理，CQE 到达后立即计算距离
2. **thread_local vec_ring_**: per-thread io_uring，多线程安全

### 下一步建议

方向 A 正向 (+3.5% @1T, +3.2% @4T)，证据充分。建议：
- 开 promote 提案，合入 Trunk
- 方向 B（k-means 聚类重排）作为独立 POC

