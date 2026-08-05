# TOPIC: multi-thread-scaling

> topic_id: multi-thread-scaling
> status: promoted
> created: 2026-08-05
> baseline_protocol: [[CON-SLA-014]] + SIFT1M@512MB / DEEP10M@2GB
> depends_on_topics: []

## 概述

建立 DiskHNSW 多线程 scaling 严格基线，覆盖 1T 至 24T 全曲线，
同步建立 hnswlib native 多线程对比基线（含 cgroup 限制 + 无限制两组）。

## Proposals

| Path | Status | Role |
|------|--------|------|
| `spec/open/proposal-multi-thread-scaling.md` | Implemented | root |
| `spec/open/proposal-4t-scaling-investigation.md` | Pending | amend (旧提案，聚焦 pipe 4T，本主题扩展) |

## Draft Clauses

无（本 POC 不新增 must 条款，仅收集证据）

## Active Hypothesis

1. **H1**: `batchSearchConcurrent` 的 mutex 去除在高并发下有可测量收益（>2% QPS）- ⚠️ 难以独立量化（与 race fix 混合）
2. **H2**: DiskHNSW scaling 在 8T-12T 后偏离线性 - ✅ 确认（8T=5.23x, 12T=6.42x, 16T=peak）
3. **H3**: hnswlib native scaling 也非完美线性 - ✅ 确认（512MB 下被内存饿死；unlimited 下 16T peak 后回退）

## POC 发现

### 发现 #1: FineRerank 懒初始化 race condition (严重)
- `searchKnn` 中 `buildFineRerank()` 无锁，多线程同时初始化导致 double free + core dump
- 修复: `std::call_once`
- 影响: Trunk `src/` 同样存在此 bug，4T+ 必崩
- **需要 bug track promote 修复**

### 发现 #2: SIFT1M 完整 scaling 曲线
- DiskHNSW (512MB cgroup): 峰值 16T=18044 QPS, 24T 回退
- hnswlib (512MB cgroup): 被内存饿死, 1T 仅 51 QPS
- hnswlib (unlimited): 峰值 16T=40358 QPS
- DiskHNSW 1T = hnswlib unlimited 的 44%（用 27% 内存）

### 发现 #3: DEEP10M scaling 曲线
- DiskHNSW (2GB cgroup): 峰值 4T=779 QPS, 8T+ 回退（I/O + 内存挤压）
- hnswlib (unlimited): 峰值 12T=12480 QPS, RSS ~6GB
- DiskHNSW 4T = hnswlib 的 11%（用 24% 内存）
- 之前 12T=2340 QPS 是白嫖数据

### 发现 #4: 三方对比 (v2 补充)
- SIFT1M 4T 是 DiskHNSW 最佳效率点：hnswlib 的 52%，内存 28%
- DEEP10M 差距更大：I/O 密集 + cgroup 挤压
- 三者 peak 线程数接近（12-16T），CPU 拓扑是天花板
- hnswlib 512MB cgroup 下 QPS 暴跌 100x+（内存饿死）

## Evidence

| File | Content |
|------|---------|
| `evidence/sift1m-scaling-20260805.md` | SIFT1M DiskHNSW + hnswlib (512MB cgroup) |
| `evidence/deep10m-scaling-20260805.md` | DEEP10M DiskHNSW (2GB cgroup) |
| `evidence/hnswlib-unlimited-20260805.md` | hnswlib unlimited memory (SIFT1M + DEEP10M) |

## Next Gate

1. **Bug fix promote**: FineRerank race condition -> bug track 提案
2. 瓶颈定位 (SIFT1M 12T+ / DEEP10M 4T+ scaling 停滞)

## Notes

- 所有代码变更在 `poc/multi-thread-scaling/` 内，不修改 Trunk `src/`
- 基线测量对齐 [[CON-SLA-014]]（drop_caches + cgroup）
- hnswlib native 对比在同一机器、同一线程数下运行
- v2 补充: hnswlib unlimited memory 对比（drop_caches only, 无 cgroup）
