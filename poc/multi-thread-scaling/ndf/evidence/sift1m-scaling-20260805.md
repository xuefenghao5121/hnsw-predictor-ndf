# Evidence: SIFT1M Multi-thread Scaling (CON-SLA-014)

> 日期: 2026-08-05
> 协议: [[CON-SLA-014]] 严格 cgroup 隔离 (drop_caches + 512MB cgroup)
> 机器: i7-13700 (8P+8E, 24 logical threads)
> 数据集: SIFT1M (128D, 1M vectors), 200 queries, k=10, ef=100

## POC 发现 #1: FineRerank 懒初始化 race condition (严重)

**症状**: 4T 首次运行 `free(): double free detected in tcache 2` + core dump
**根因**: `searchKnn` 中 `buildFineRerank()` 懒初始化无锁，多线程同时进入导致：
- `node_slot_table_` 被 `assign()` 多次（vector 析构 double free）
- `vec_ring_` 被 `make_unique` 多次（IoUring 析构 double free）
**修复**: `std::call_once` 保证只初始化一次
**影响**: Trunk `src/` 同样存在此 bug（4T+ 必崩），需要 promote 修复

## POC 发现 #2: Scaling 曲线

### DiskHNSW (512MB cgroup)

| Threads | QPS | Scaling | Recall | Mean(ms) | P50(ms) | P95(ms) | P99(ms) | RSS(MB) |
|---------|-----|---------|--------|----------|---------|---------|---------|---------|
| 1T | 2744 | 1.00x | 95.80% | 0.36 | 0.33 | 0.67 | 0.86 | 197 |
| 2T | 5680 | 2.07x | 95.80% | 0.35 | 0.33 | 0.58 | 0.64 | 199 |
| 4T | 9657 | 3.52x | 95.80% | 0.41 | 0.35 | 0.75 | 0.89 | 202 |
| 8T | 14350 | 5.23x | 95.80% | 0.54 | 0.43 | 1.24 | 1.46 | 210 |
| 12T | 17610 | 6.42x | 95.80% | 0.64 | 0.57 | 1.38 | 1.53 | 217 |
| 16T | 18044 | 6.58x | 95.80% | 0.83 | 0.63 | 1.71 | 1.83 | 225 |
| 24T | 17288 | 6.30x | 95.80% | 1.22 | 1.15 | 2.06 | 2.71 | 240 |

**cgroup**: peak=512MB, oom=0, anon~600KB, file~283-330MB (page cache for vecblocks)

### hnswlib Native (512MB cgroup)

| Threads | QPS | Scaling | Recall | Mean(ms) | P50(ms) | P95(ms) | P99(ms) | RSS(MB) |
|---------|-----|---------|--------|----------|---------|---------|---------|---------|
| 1T | 51 | 1.00x | 98.30% | 19.47 | 19.03 | 30.78 | 35.22 | 503 |
| 2T | 121 | 2.36x | 98.30% | 16.48 | 16.17 | 27.13 | 29.80 | 507 |
| 4T | 214 | 4.20x | 98.30% | 18.46 | 18.80 | 28.72 | 32.71 | 507 |
| 8T | 441 | 8.64x | 98.30% | 17.63 | 17.51 | 28.63 | 33.48 | 507 |
| 12T | 496 | 9.72x | 98.30% | 23.30 | 22.89 | 37.17 | 43.35 | 506 |
| 16T | 648 | 12.71x | 98.30% | 23.54 | 22.96 | 35.54 | 45.53 | 456 |
| 24T | 731 | 14.33x | 98.30% | 31.45 | 30.45 | 46.76 | 54.84 | 508 |

**注**: hnswlib RSS ~507MB 接近 512MB cgroup 上限。drop_caches 后 mmap 页被驱逐，
cgroup 内 page cache 预算极小（~5MB），导致每次访问都触发 page fault + disk I/O。
QPS 极低（51-731）是因为 hnswlib 在 512MB 限制下被内存饿死。

## 分析

### Scaling 特性

**DiskHNSW**:
- 1T→4T: 近线性 (3.52x)
- 4T→12T: 1.82x（偏离线性，瓶颈出现）
- 12T→16T: 几乎平 (1.02x)，峰值在 12-16T
- 24T: 回退 (-4.2% vs 16T)，线程竞争开销 > 收益
- 瓶颈候选: BlockCache LRU 锁、pread VFS 竞争

**hnswlib Native** (512MB 限制下):
- 极慢但仍在 scaling（page fault 并行化）
- 24T 仍未到峰值（受限于 512MB 内存而非 CPU）

### 对比 (DiskHNSW vs hnswlib, 512MB cgroup)

| Threads | DiskHNSW QPS | hnswlib QPS | DiskHNSW 优势 |
|---------|-------------|-------------|--------------|
| 1T | 2744 | 51 | **53.7x** |
| 4T | 9657 | 214 | **45.1x** |
| 12T | 17610 | 496 | **35.5x** |
| 24T | 17288 | 731 | **23.6x** |

**结论**: 在 512MB 内存限制下，DiskHNSW 全面碾压 hnswlib（23-54x）。
hnswlib 被 cgroup 内存饿死，DiskHNSW 的磁盘+PQ+page cache 架构在内存受限场景优势巨大。

### vs 之前基线对比

| 指标 | CHR-006 基线 (2026-08-03) | POC 基线 (2026-08-05) | 变化 |
|------|--------------------------|----------------------|------|
| 1T QPS | 2309 | 2744 | +18.9% |
| 4T QPS | 6060 | 9657 | +59.4% |

**差异原因**:
1. POC 修复了 FineRerank race condition (std::call_once)
2. POC 去掉了 batchSearchConcurrent 的无用 mutex
3. POC 多线程 warmup（之前 warmup 是单线程）
4. POC per-query latency 收集（更精确计时）

## 假设验证

| 假设 | 结论 | 证据 |
|------|------|------|
| H1: 去 mutex 有 >2% 收益 | ⚠️ 难以独立量化（与 race fix 混合） | 4T 从崩溃->9657 QPS |
| H2: 8-12T 偏离线性 | ✅ 确认 | 8T=5.23x, 12T=6.42x（<12x 线性） |
| H3: native 也非线性 | ✅ 确认（但原因是内存饿死） | 24T=14.33x（<24x 线性） |

## 下一步

1. **Bug fix promote**: FineRerank race condition 是严重 bug，应走 bug track promote 修复 Trunk
2. **DEEP10M scaling**: 待跑
3. **瓶颈定位**: 12T+ scaling 停滞，需 perf 分析
