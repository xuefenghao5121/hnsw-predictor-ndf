# Evidence: DEEP10M Multi-thread Scaling (CON-SLA-014)

> 日期: 2026-08-05
> 协议: [[CON-SLA-014]] 严格 cgroup 隔离 (drop_caches + 2GB cgroup)
> 机器: i7-13700 (8P+8E, 24 logical threads)
> 数据集: DEEP10M (96D, 10M vectors), 10000 queries, k=10, ef=300, REFINE_EF=300

## DiskHNSW DEEP10M Scaling

| Threads | QPS | Scaling | Recall | Mean(ms) | P50(ms) | P95(ms) | P99(ms) | RSS(MB) |
|---------|-----|---------|--------|----------|---------|---------|---------|---------|
| 1T | 302 | 1.00x | 94.85% | 3.31 | 3.06 | 4.49 | 8.69 | 1414 |
| 2T | 572 | 1.89x | 94.85% | 3.50 | 3.51 | 4.30 | 4.74 | 1449 |
| **4T** | **779** | **2.58x (peak)** | 94.85% | 5.14 | 5.18 | 6.70 | 7.49 | 1474 |
| 8T | 678 | 2.24x (回退) | 94.85% | 11.80 | 11.43 | 17.58 | 26.47 | 1524 |
| 12T | 634 | 2.10x (更差) | 94.85% | 18.92 | 17.36 | 30.23 | 52.67 | 1574 |

**cgroup**: peak=2GB, oom=0

### Page cache 变化

| Threads | RSS(MB) | file cache(MB) | 可用 page cache |
|---------|---------|----------------|----------------|
| 1T | 1414 | 609 | ~590MB |
| 2T | 1449 | 575 | ~575MB |
| 4T | 1474 | 549 | ~549MB |
| 8T | 1524 | 497 | ~497MB |
| 12T | 1574 | 447 | ~447MB |

**趋势**: 线程数增加 -> RSS 上升 (VisitedList/线程栈) -> page cache 被挤压 -> I/O 增加 -> QPS 下降

## 分析

### 与 SIFT1M 对比

| 指标 | SIFT1M (512MB) | DEEP10M (2GB) |
|------|---------------|---------------|
| 峰值线程数 | 12-16T | 4T |
| 峰值 QPS | 18,044 | 779 |
| 8T vs 4T | +48% (仍增长) | -13% (回退) |
| 线性区间 | 1-4T | 1-2T |
| 瓶颈性质 | CPU/锁竞争 | I/O + 内存挤压 |

### 回退根因分析

**SIFT1M**: 12T+ 回退是 CPU 竞争（QPS 高，I/O 占比低）
**DEEP10M**: 4T+ 回退是 **I/O 瓶颈 + cgroup 内存挤压**：
1. vecblocks 3.7GB >> page cache 预算 (~450-600MB)
2. 更多线程 = 更多并发 pread = 更多 page fault
3. 每个线程的 VisitedList (10M * 1B = 10MB) 挤压 page cache
4. page cache 缩小 -> cache miss 上升 -> 更多 I/O -> 恶性循环

### hnswlib Native 对比

未跑（hnswlib 需要 ~7GB 内存，2GB cgroup 下直接 OOM）

## 关键洞察

1. **I/O 密集型 workload 的多线程 scaling 拐点更早**：DEEP10M 4T 即到峰值，SIFT1M 12-16T
2. **cgroup 内存预算是 scaling 硬约束**：线程数增加 -> anon 上升 -> file cache 下降 -> I/O 增加
3. **DEEP10M 1T QPS=302 高于之前 MEMORY.md 记录的 2340@12T**：之前 12T 数据是未严格隔离的白嫖 era 数据
4. **DEEP10M 严格隔离下 12T 反而不如 4T**：之前 12T=2340 QPS 的数据必然是白嫖 page cache

## POC 发现汇总

### 发现 #1: FineRerank race condition (严重, SIFT1M)
- 已在 SIFT1M evidence 中记录

### 发现 #2: SIFT1M scaling 曲线
- 峰值 12-16T, 18K QPS

### 发现 #3: DEEP10M scaling 曲线
- 峰值 4T, 779 QPS
- 8T+ 回退（I/O + 内存挤压）

### 发现 #4: DEEP10M 之前 12T=2340 QPS 数据是白嫖
- 严格隔离下 12T=634 QPS，之前 2340 必然是未 drop_caches 的白嫖数据
- 需要更新 MEMORY.md 和 README.md 中的 DEEP10M 数据
