# TOPIC: multi-thread-scaling

> topic_id: multi-thread-scaling
> status: exploring (resumed 2026-08-05)
> created: 2026-08-05
> baseline_protocol: [[CON-SLA-014]] + SIFT1M@512MB / DEEP10M@2GB
> explore_surface: mt-scaling,fine-rerank
> baseline_trunk_sha: unknown-pre-policy
> baseline_status: stale
> depends_on_topics: []
> conflicts_with_topics: []

## 概述

建立 DiskHNSW 多线程 scaling 严格基线，覆盖 1T 至 24T 全曲线，
同步建立 hnswlib native 多线程对比基线（含 cgroup 限制 + 无限制两组）。
关注两个维度：**多线程扩展性** + **相对 hnswlib 无约束的性能差距**。

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
4. **H4**: DiskHNSW vs hnswlib(unlimited) 差距随数据规模拉大 - ✅ 确认（SIFT1M 44-52%, DEEP10M 5-17%）

## POC 发现

### 发现 #1: FineRerank 懒初始化 race condition (严重)
- `searchKnn` 中 `buildFineRerank()` 无锁，多线程同时初始化导致 double free + core dump
- 修复: `std::call_once` -> **已 promote 到 Trunk** (commit 1d14de7)

### 发现 #2: SIFT1M 完整 scaling 曲线
- DiskHNSW (512MB cgroup): 峰值 16T=18044 QPS, 24T 回退
- hnswlib (512MB cgroup): 被内存饿死, 1T 仅 51 QPS
- hnswlib (unlimited): 峰值 16T=40358 QPS

### 发现 #3: DEEP10M scaling 曲线
- DiskHNSW (2GB cgroup): 峰值 4T=779 QPS, 8T+ 回退（I/O + 内存挤压）
- hnswlib (unlimited): 峰值 12T=12480 QPS, RSS ~6GB
- 之前 12T=2340 QPS 是白嫖数据

### 发现 #4: 三方对比 (v2 补充)
- SIFT1M 4T 是 DiskHNSW 最佳效率点：hnswlib 的 52%，内存 28%
- DEEP10M 差距更大：I/O 密集 + cgroup 挤压
- 三者 peak 线程数接近（12-16T），CPU 拓扑是天花板
- hnswlib 512MB cgroup 下 QPS 暴跌 100x+（内存饿死）

### 发现 #5: 瓶颈定位 - WILLNEED 内核锁竞争 (v3)
- 12T 新增 6.27% kernel 锁开销，全部来自 `posix_fadvise(WILLNEED)` 调用链
- VisitedList memset 翻倍 (5.38% -> 10.29%)
- BlockCache LRU 锁、分配器均非瓶颈

## 相对 hnswlib(unlimited) 性能差距分析

### SIFT1M (DiskHNSW 512MB vs hnswlib unlimited)

| Threads | DiskHNSW QPS | hnswlib QPS | 比值 | DiskHNSW RSS | hnswlib RSS | 内存比 |
|---------|-------------|-------------|------|-------------|-------------|--------|
| 1T | 2,744 | 6,245 | 44% | 197MB | 726MB | 27% |
| 4T | 9,657 | 18,496 | 52% | 202MB | 732MB | 28% |
| 12T | 17,610 | 30,496 | 58% | 217MB | 747MB | 29% |
| 16T | 18,044 | 40,358 | 45% | 225MB | 755MB | 30% |
| 24T | 17,288 | 37,555 | 46% | 240MB | 770MB | 31% |

- **最佳效率点 12T**: 58% QPS / 29% 内存
- **QPS/MR 效率比**: DiskHNSW 1T=13.9, hnswlib 1T=8.6 -> **1.6x 内存效率优势**

### DEEP10M (DiskHNSW 2GB vs hnswlib unlimited)

| Threads | DiskHNSW QPS | hnswlib QPS | 比值 | DiskHNSW RSS | hnswlib RSS | 内存比 |
|---------|-------------|-------------|------|-------------|-------------|--------|
| 1T | 302 | 1,806 | 17% | 1,414MB | 5,967MB | 24% |
| 4T | 779 | 7,226 | 11% | 1,474MB | 6,024MB | 24% |
| 12T | 634 | 12,480 | 5% | 1,574MB | 6,177MB | 25% |

- **差距随规模拉大**: SIFT1M 44-58% -> DEEP10M 5-17%
- **根因**: DEEP10M vecblocks 3.7GB >> page cache 预算，I/O 成为瓶颈
- **scaling 拐点提前**: SIFT1M 12-16T peak -> DEEP10M 4T peak

### 差距来源分解

| 来源 | SIFT1M 影响 | DEEP10M 影响 | 可优化? |
|------|------------|-------------|--------|
| PQ 近似 vs 精确距离 | recall -2.5pp, QPS 基线影响 | recall -0.27pp | ❌ 架构代价 |
| 磁盘 I/O (FineRerank pread) | 小 (496MB vecblocks, page cache 48%) | 大 (3.7GB vecblocks, page cache 10%) | ✅ P3 CSR 上磁盘 |
| cgroup 内存挤压 | 轻微 (RSS 197MB / 512MB) | 严重 (RSS 1.4GB / 2GB) | ✅ 算法优化 |
| WILLNEED 锁竞争 (12T+) | 6.27% | 未测（但 WILLNEED 在 DEEP10M 无收益） | ✅ 方向 A/B |
| VisitedList memset | 10.29% (12T) | 类似 | ✅ 方向 C |

## 优化方向记录（待决策）

| ID | 方向 | 目标 | 预期收益 | 复杂度 | 影响范围 |
|----|------|------|---------|--------|---------|
| **A** | WILLNEED 后台线程化 | 消除 12T+ 内核锁竞争 | SIFT1M 12T +10-15% QPS | 中 | disk_hnsw.cpp WILLNEED 路径 |
| **B** | WILLNEED 自适应禁用 (T≥8) | 快速消除竞争 | SIFT1M 12T +5-10% QPS | 低 | 环境变量检查 |
| **C** | VisitedList 线程局部池 | 减少 memset cache bouncing | SIFT1M 12T +3-5% QPS | 中 | searchKnn VisitedList 管理 |
| **D** | 缩小 PQ recall 差距 | SIFT1M recall 95.8% -> 98%+ | recall +2pp, QPS 可能下降 | 高 | PQ 编码/搜索逻辑 |
| **E** | DEEP10M I/O 优化 (P3 CSR 上磁盘) | 减少 I/O 量 | DEEP10M QPS 大幅提升 | 很高 | 架构级改动 |
| **F** | flat_vec_cache 调优 | 提高热向量命中率 | SIFT1M +5%, DEEP10M +10% | 低 | FLAT_VEC_MB 参数 |

## Evidence

| File | Content |
|------|---------|
| `evidence/sift1m-scaling-20260805.md` | SIFT1M DiskHNSW + hnswlib (512MB cgroup) |
| `evidence/deep10m-scaling-20260805.md` | DEEP10M DiskHNSW (2GB cgroup) |
| `evidence/hnswlib-unlimited-20260805.md` | hnswlib unlimited memory (SIFT1M + DEEP10M) |
| `evidence/bottleneck-profiling-20260805.md` | 4T vs 12T perf profile, WILLNEED 锁竞争 |

## Next Gate

1. ~~Bug fix promote~~ ✅ Trunk commit 1d14de7
2. ~~瓶颈定位~~ ✅ WILLNEED 内核锁竞争 (6.27%) + VisitedList memset (10.29%)
3. **决策**: 选择优化方向 A-F 或关闭主题

## Notes

- 所有代码变更在 `poc/multi-thread-scaling/` 内，不修改 Trunk `src/`
- 基线测量对齐 [[CON-SLA-014]]（drop_caches + cgroup）
- hnswlib native 对比在同一机器、同一线程数下运行
- v2 补充: hnswlib unlimited memory 对比（drop_caches only, 无 cgroup）
- v3 补充: perf profiling 瓶颈定位
- 两个关注维度：多线程扩展性 + 相对 hnswlib 无约束性能差距
