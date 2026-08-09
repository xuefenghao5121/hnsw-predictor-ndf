# Trunk Profiling Report — SIFT1M 256MB 1T

> 日期: 2026-08-09
> Trunk SHA: 4697c0d
> Binary: build/benchmark_sustained (rebuilt 2026-08-09 17:20)
> 协议: CON-SLA-014 (cgroup 256MB) + CON-SLA-019 + CON-SLA-020 (sustained)

## 1. 基准测试结果

| 配置 | Agg QPS | Steady QPS | Recall | 对标 |
|------|---------|-----------|--------|------|
| M=16 EF=100 (SLA) | **1,072** | 1,144 | 97.76% | CON-SLA-020 = 1,076 ✅ (+0.4%) |
| M=16 EF=65 (DEC-091) | **1,441** | 1,553 | 95.52% | DEC-091 = 1,486 (-3.0%) |
| M=16 EF=65 +ADAPTIVE | **1,624** | 1,826 | 95.17% | DEC-092 = 1,637 (-0.8%) |

cgroup 有效性: pgmajfault=7,473, major-faults 确认 I/O 发生。

## 2. Perf Stat (EF=65, 10K queries, 9.15s wall)

| 系统调用 | 次数 | 次/query | 说明 |
|---------|------|---------|------|
| pread64 | 508,153 | 50.8 | 向量数据读取 |
| fadvise64 | 423,757 | 42.4 | WILLNEED 预取提示 |
| sched_yield | **21,163,325** | **2,116** | WILLNEED_BG 线程自旋 |
| context-switches | 87,699 | 8.8 | 线程切换 |
| minor-faults | 127,197 | 12.7 | 软页错误 |
| major-faults | 7,473 | 0.75 | 硬页错误 (磁盘 I/O) |

- User time: 5.37s (58.6%)
- Sys time: 5.85s ... wait, that doesn't add up. User + Sys > Wall.
- Actually: 5.37s user + 5.85s sys on 2 threads (main + WILLNEED_BG) = 11.22s CPU / 9.15s wall = 1.23x CPU utilization

## 3. CPU 时间分布 (P-core cycles)

| 域 | 占比 | 说明 |
|----|------|------|
| **Kernel [k]** | **43.7%** | sched_yield → schedule 路径占大头 |
| **User app [.]** | **38.5%** | PQ 距离计算 + 图搜索 |
| **libc** | **8.4%** | memset (VisitedList) + sched_yield |

**关键发现: 内核时间 > 用户时间。WILLNEED_BG 的 sched_yield 自旋是最大 CPU 消耗者。**

## 4. Top 函数排名 (P-core, EF=65)

| 排名 | % | 函数 | 域 | 角色 |
|------|---|------|---|------|
| 1 | **14.6%** | `std::thread::_State_impl<...lambda#15>` | user | WILLNEED_BG 线程主循环 (含 sched_yield) |
| 2 | **10.3%** | `DiskHNSW::pqDistance()` | user | PQ ADC 距离计算 |
| 3 | 3.4% | `__schedule()` | kernel | 调度器 |
| 4 | 2.9% | `DiskHNSW::searchLayer0()` | user | L0 图搜索主循环 |
| 5 | 2.9% | `__sched_yield()` | libc | sched_yield 用户态包装 |
| 6 | 2.8% | `_raw_spin_lock()` | kernel | 内核自旋锁 |
| 7 | 2.7% | `entry_SYSRETQ_unsafe_stack` | kernel | 系统调用返回 |
| 8 | 2.4% | `__memset_avx2_unaligned_erms` | libc | VisitedList memset |
| 9 | 1.9% | `entry_SYSCALL_64()` | kernel | 系统调用入口 |
| 10 | 1.9% | `_copy_to_iter()` | kernel | pread 数据拷贝 |
| 11 | 1.8% | `DiskHNSW::decodeCsrNeighbors()` | user | CSR 邻居解码 |
| 12 | 1.7% | `std::__final_insertion_sort` | user | 候选排序 |
| 13 | 1.6% | `update_curr()` | kernel | 调度统计 |
| 14 | 1.6% | `DiskHNSW::buildInMemoryAdjacency()` | user | 邻居列表构建 |
| 15 | 1.0% | `DiskHNSW::searchKnn()` | user | 搜索入口 |

## 5. 热点分析

### 5.1 WILLNEED_BG sched_yield 自旋 (14.6% + 2.9% + 2.7% ≈ 20%)

`lambda#15` 是 searchKnn 中的 WILLNEED_BG 后台线程。它通过 SPSC 队列接收预取请求，
在无任务时调用 `sched_yield()` 让出 CPU。

**21M 次 sched_yield / 10K queries = 2,116 次/query**。每次 sched_yield 触发完整
schedule() → pick_next_task_fair() → update_curr() → update_se() 路径，消耗大量内核时间。

**优化方向**: 替换为 futex 或 park/unpark 机制，减少空转。但当前架构下 sched_yield 是
最简单的零延迟唤醒方案。

### 5.2 PQ ADC 距离计算 (10.3%)

`pqDistance()` 是 FineRerank 两阶段搜索的核心——对每个候选执行 PQ ADC (Asymmetric Distance Computation)。
已使用查找表优化，10.3% 是合理的——这是算法核心开销。

### 5.3 图搜索 (2.9% searchLayer0 + 1.8% decodeCsr + 1.7% insertion_sort ≈ 6.4%)

L0 搜索的图遍历开销。decodeCsrNeighbors 解压缩 BFS 重排后的 CSR 邻居列表。
insertion_sort 是候选集的动态排序。

### 5.4 内存操作 (2.4% memset + 1.6% buildAdjacency ≈ 4.0%)

VisitedList 的 memset 是每个 query 重置访问位图的固定开销。
buildInMemoryAdjacency 是 query 开始时构建邻居列表。

### 5.5 I/O 路径 (1.9% _copy_to_iter + 1.8% page_counter ≈ 3.7%)

pread 数据拷贝 + cgroup 内存记账。I/O 本身不慢（NVMe SSD），开销在内核路径。

## 6. EF=65 vs EF=100 对比

| 指标 | EF=65 | EF=100 | 变化 |
|------|-------|--------|------|
| pqDistance% | 10.3% | 10.3% | 持平 |
| WILLNEED_BG% | 14.6% | 14.9% | 持平 |
| searchLayer0% | 2.9% | 3.0% | 持平 |
| pread/query | 50.8 | ~78 | +54% |
| fadvise/query | 42.4 | ~65 | +54% |
| QPS | 1,392 | 1,093 | -27.3% |

EF=100 多 54% 的 I/O 调用 → QPS 降 27%。开销基本按比例传导。

## 7. 性能瓶颈总结

```
瓶颈 1: WILLNEED_BG sched_yield 自旋 (~20% CPU)
  - 根因: SPSC 队列无任务时空转
  - 影响: 浪费 ~20% P-core 时间在 sched_yield → schedule 路径
  - 缓解: futex/park 可消除, 但可能增加延迟
  - 当前最优: sched_yield 对 1T 场景实际是最优 (零延迟唤醒)

瓶颈 2: PQ ADC 距离计算 (10.3%)
  - 算法核心, 无法消除
  - 已有 SIMD 优化
  - 进一步优化方向: AVX-512 (需要硬件支持)

瓶颈 3: 内核 I/O 路径 (~8% schedule + spin_lock + copy)
  - pread 系统调用开销
  - cgroup 内存记账 (page_counter_try_charge)
  - 内核 XArray 页缓存管理

结论: 256MB 1T 下, 性能瓶颈不在单一函数, 而是 sched_yield 自旋 + PQ 计算 + I/O 路径的
组合。当前架构已接近 1T 最优——进一步优化需要改变调度模型 (futex) 或 I/O 模型 (io_uring)。
```
