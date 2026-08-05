# Proposal: 多线程 Scaling 严格基线

> track: poc
> 日期: 2026-08-05
> Status: Implemented on 2026-08-05
> 关联: [[CHR-006]]、[[CON-SLA-014]]、[[CON-HONEST-002]]、[[CON-POC-001]]、[[BEH-018]]、[[BEH-025]]
> 扩展: `proposal-4t-scaling-investigation.md`（旧提案聚焦 pipe 4T，本提案扩展为完整 scaling 基线）

## 1. 问题陈述

当前 [[CHR-006]] 严格隔离基线只有 1T 和 4T 两个数据点（SIFT1M: 2309/6060 QPS）。
缺少完整的 scaling 曲线（2T/8T/12T/16T/24T），无法判断：

- 线性扩展区间在哪里结束
- 瓶颈是什么（BlockCache 锁、pread VFS 竞争、分配器、GraphPrefetcher、io_uring）
- hnswlib native 在同等线程数下的对比（当前 native benchmark 只支持单线程）
- DEEP10M 多线程 scaling 特性（当前只有 12T 一个点：2340 QPS）

### 已知问题

1. `batchSearchConcurrent` 中有不必要的 `std::mutex`（每个线程写 `results[i]`，i 互斥，无竞争）
2. benchmark_diskhnsw 多线程模式无 per-query latency（用 `total_s / num_query` 近似）
3. benchmark_hnswlib_native 完全不支持多线程，无法做公平对比
4. 多线程 warmup 缺失（首次并发搜索有噪声）

## 2. 探索目标（非 Trunk SLA）

### 2.1 建立完整 scaling 曲线

**协议**: [[CON-SLA-014]] 严格 cgroup 隔离

| 数据集 | cgroup | 线程数 | 指标 |
|--------|--------|--------|------|
| SIFT1M | 512MB | 1/2/4/8/12/16/24 | QPS, recall, mean/p50/p95/p99, RSS |
| DEEP10M | 2GB | 1/2/4/8/12 | QPS, recall, mean/p50/p95/p99, RSS |

### 2.2 hnswlib native 多线程对比

同等线程数下对比，量化 DiskHNSW 的相对性能。

### 2.3 瓶颈定位（若 scaling < 线性）

候选瓶颈：
- BlockCache 内部锁（LRU 更新、hash table）
- pread/VFS 层竞争（多线程同时读不同 offset）
- GraphPrefetcher 锁
- 内存分配器（VisitedList alloc/free）
- io_uring 提交队列竞争

## 3. 代码变更（全部在 `poc/` 内）

| 文件 | 变更 | 说明 |
|------|------|------|
| `poc/multi-thread-scaling/benchmark_diskhnsw_mt.cpp` | 基于 Trunk 修改 | 加 per-query latency、MT warmup |
| `poc/multi-thread-scaling/benchmark_hnswlib_native_mt.cpp` | 基于 Trunk 修改 | 加 NUM_THREADS 支持 |
| `poc/multi-thread-scaling/disk_hnsw_mt.cpp` | 基于 Trunk 修改 | 去掉 batchSearchConcurrent 无用 mutex |
| `poc/multi-thread-scaling/run_scaling.sh` | 新建 | 自动 sweep 脚本 |

**不修改 Trunk `src/`**（[[BEH-018]] 第 6 条）。

## 4. 不做的事

- 不改 Trunk `src/` 生产代码
- 不写 stable must SLA
- 不引用旧白嫖 era 数据作为基线
- 不把 POC 数字写入 [[CON-SLA-*]]

## 5. 晋升条件（未来）

若 POC 发现有效的优化（如去 mutex 有可测量收益），另开 **promote** 提案，
引用本主题 `TOPIC.md`，走 [[BEH-019]] 干净合入。
