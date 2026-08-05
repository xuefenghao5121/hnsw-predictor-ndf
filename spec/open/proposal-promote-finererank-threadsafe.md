# Proposal: Promote - FineRerank 线程安全修复 + 多线程 Benchmark 补全

> track: promote
> 日期: 2026-08-05
> Status: Implemented on 2026-08-05
> POC 主题: `poc/multi-thread-scaling/ndf/TOPIC.md`
> POC 证据:
> - `poc/multi-thread-scaling/ndf/evidence/sift1m-scaling-20260805.md`
> - `poc/multi-thread-scaling/ndf/evidence/deep10m-scaling-20260805.md`
> - `poc/multi-thread-scaling/ndf/evidence/hnswlib-unlimited-20260805.md`
> 关联: [[BEH-001]]、[[BEH-007]]、[[BEH-002]]、[[CHR-006]]、[[CON-SLA-014]]

## 1. Promote 来源

POC 主题 `multi-thread-scaling` 在探索中发现 Trunk `src/` 中的严重 bug 并在 POC 中验证修复。
现将验证通过的修复干净合入 Trunk。

## 2. Promote 内容

### 2.1 Bug Fix: FineRerank 懒初始化 race condition

**POC 文件**: `poc/multi-thread-scaling/disk_hnsw_mt.cpp` (已验证)

**Trunk 文件**: `src/core/disk_hnsw.cpp`

**问题**: `searchKnn()` (line ~1691-1697) 中 FineRerank 懒初始化无锁，多线程同时调用 `buildFineRerank()` 导致 double free + core dump (4T+ 必崩)。

**修复**:
- `#include <mutex>` 新增头文件
- `std::call_once` 包裹 `buildFineRerank()` 调用
- 仅 +8 行代码

**POC 验证结果**:
- 4T 崩溃 -> 修复后 4T QPS=9657, recall=95.80% ✅
- 1T-24T 全线程数通过 ✅
- [[CON-SLA-014]] 严格 cgroup 隔离验证通过 ✅

### 2.2 Bug Fix: batchSearchConcurrent 无用 mutex

**Trunk 文件**: `src/core/disk_hnsw.cpp`

**问题**: `batchSearchConcurrent()` (line ~2780) 中 `std::mutex mtx` + `std::lock_guard` 保护 `results[i]` 写入，但每个线程的 `i` 来自 `atomic<size_t>` 互斥分配，不可能竞争。mutex 是无谓开销。

**修复**: 删除 `std::mutex mtx` 声明和 `std::lock_guard` 包裹。

### 2.3 Benchmark 补全: benchmark_diskhnsw 多线程 warmup + per-query latency

**Trunk 文件**: `src/benchmark/benchmark_diskhnsw.cpp`

**问题**:
1. 多线程模式 warmup 只走单线程（首次并发搜索有噪声）
2. 多线程模式无 per-query latency（用 `total_s / num_query` 近似，不准确）

**修复**:
- `#include <thread>` `#include <atomic>` 新增头文件
- 多线程 warmup（与测试线程数一致）
- 多线程模式下 inline 实现 thread pool + per-query latency 收集（不再调用 `batchSearchConcurrent`）

### 2.4 Benchmark 补全: benchmark_hnswlib_native 多线程支持

**Trunk 文件**: `src/benchmark/benchmark_hnswlib_native.cpp`

**问题**: 完全不支持多线程，无法做多线程对比。

**修复**:
- `#include <thread>` `#include <atomic>` 新增头文件
- `NUM_THREADS` 环境变量支持（与 DiskHNSW benchmark 一致）
- 多线程 warmup + per-query latency

## 3. 不涉及 draft->stable 条款变更

本次 promote 不新增/修改 L0/L1 条款。修复的是 L2 实现层 bug（race condition），
现有 [[BEH-001]]、[[BEH-007]]、[[BEH-002]] stable 条款不受影响（行为契约不变，只是修复并发崩溃）。

## 4. 验证计划

### 场景5: 编译验证
`make bench` 编译通过，无 error。

### 场景6: 性能验证
对齐 [[CON-SLA-014]] 严格 cgroup 隔离，验证 [[CHR-006]] stable SLA：

| 指标 | SLA | POC 实测 |
|------|-----|---------|
| Recall@10 (1T) | ≥ 95% | 95.80% ✅ |
| QPS (1T, 512MB) | ≥ 2000 | 2744 ✅ |
| QPS (4T, 512MB) | ≥ 5000 | 9657 ✅ (之前必崩) |
| RSS (1T) | ≤ 300MB | 197MB ✅ |
| RSS (4T) | ≤ 450MB | 202MB ✅ |
| oom | = 0 | 0 ✅ |

**核心验证点**: 4T 不再崩溃，QPS ≥ 5000。

## 5. 干净合入说明

从 POC 文件到 Trunk 的映射：
- `poc/multi-thread-scaling/disk_hnsw_mt.cpp` -> `src/core/disk_hnsw.cpp` (call_once + 去 mutex)
- `poc/multi-thread-scaling/benchmark_diskhnsw_mt.cpp` -> `src/benchmark/benchmark_diskhnsw.cpp`
- `poc/multi-thread-scaling/benchmark_hnswlib_native_mt.cpp` -> `src/benchmark/benchmark_hnswlib_native.cpp`

POC 文件保留在 `poc/multi-thread-scaling/` 作为探索证据，不被删除。
