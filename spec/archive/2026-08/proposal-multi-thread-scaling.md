# Proposal: 多线程 Scaling 基线 + 拓展性优化

> track: poc
> 日期: 2026-08-05 (amended 2026-08-05)
> Status: Implemented on 2026-08-05
> 关联: [[CHR-006]]、[[CON-SLA-014]]、[[CON-SLA-016]]、[[CON-HONEST-002]]、[[CON-POC-001]]、[[BEH-018]]、[[BEH-025]]
> 扩展: `proposal-4t-scaling-investigation.md`（旧提案聚焦 pipe 4T，本提案扩展）
> 依赖主题: `perf-gap-4t`（已 promoted，FVC 默认值 + 256MB SLA）

## 1. 问题陈述

### 1.1 基线建立 (已完成)

建立完整的 DiskHNSW 多线程 scaling 曲线，同步建立 hnswlib native 多线程对比基线。

### 1.2 拓展性优化 (本阶段目标)

**新基线 (post-race-fix Trunk, FVC=160, 512MB cgroup) 显示 scaling 效率递减：**

| 线程数 | QPS | Scaling | 效率 |
|--------|-----|---------|------|
| 1T | 3,147 | 1.0x | 100% |
| 4T | 10,723 | 3.4x | 85% |
| 12T | 17,207 | 5.5x | 46% |
| **24T (peak)** | **19,766** | **6.3x** | **26%** |

**256MB cgroup 更早进入平台期：**

| 线程数 | QPS | Scaling | 效率 |
|--------|-----|---------|------|
| 1T | 2,564 | 1.0x | 100% |
| 4T | 6,882 | 2.7x | 67% |
| **12T+ (plateau)** | **~10,700** | **4.2x** | **~18%** |

**perf 已定位的瓶颈 (12T)：**
1. `posix_fadvise(WILLNEED)` 内核锁竞争 -- 6.27% (osq_lock + queued_spin_lock + down_read)
2. VisitedList memset -- 10.29% (1MB memset per search, cache bouncing)

**目标：通过消除 12T+ 瓶颈，提升高并发 scaling 效率。**

## 2. 探索方向 (优化阶段)

### 方向 A: WILLNEED 后台线程化 (中复杂度)

将 `posix_fadvise(WILLNEED)` 从搜索线程移到后台 I/O 线程，消除 kernel 锁竞争。

- 预期: 512MB 12T +10-15% QPS (消除 6.27% 锁开销)
- 风险: 后台线程增加 anon 内存 (~8MB stack + queue)，256MB 下需验证

### 方向 B: WILLNEED 自适应禁用 (低复杂度)

T≥8 时自动禁用 WILLNEED（锁竞争 > readahead 收益）。

- 预期: 512MB 12T +5-10% QPS
- 风险: 256MB 1T 仍需 WILLNEED (17.7x 加速)，不能全局禁用

### 方向 C: VisitedList 线程局部池 (中复杂度)

复用 VisitedList 避免每次 1MB memset。

- 预期: 512MB 12T +3-5% QPS
- 注: perf-gap-4t D4 测试 thread_local 池化反而 -15% (但那是 4T，12T 收益可能不同)
- 替代方案: pre-allocated pool (非 thread_local)

## 3. 已完成的工作

### 3.1 基线 (512MB, 256MB, 1-24T) ✅
- SIFT1M 512MB scaling sweep (post-race-fix re-baseline)
- SIFT1M 256MB scaling sweep
- hnswlib unlimited memory 对比 (SIFT1M + DEEP10M)
- DEEP10M scaling sweep

### 3.2 发现 ✅
- FineRerank race condition → 已 promote (Trunk commit 1d14de7)
- 瓶颈定位: WILLNEED 锁 + VisitedList memset
- 6 个优化方向已记录

## 4. 验证协议

所有测试对齐 [[CON-SLA-014]]：drop_caches + cgroup。
512MB 用 FVC=160，256MB 用 FVC=64。
对比目标：新基线 (512MB 24T=19766, 256MB 24T=10922)。

## 5. 不做的事

- 不改 Trunk `src/`（方向 A/B/C 在 POC 内实现验证）
- 不写 stable must SLA
- 不引用旧白嫖 era 数据

## 6. 晋升条件

若某方向验证有效（12T+ QPS 提升 >5%），另开 promote 提案，
引用本主题 TOPIC.md，走 [[BEH-019]] 干净合入。
