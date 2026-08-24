# Evidence: hnswlib Native Unlimited Memory Scaling

> 日期: 2026-08-05
> 协议: drop_caches only (NO cgroup, 无内存限制)
> 机器: i7-13700 (8P+8E, 24 logical threads)
> 目的: 补充 hnswlib 在内存充足时的 scaling 基线，与 DiskHNSW (cgroup 限制下) 做公平对比

## hnswlib Native SIFT1M (unlimited memory)

| Threads | QPS | Scaling | Recall | Mean(ms) | P50(ms) | P95(ms) | P99(ms) | RSS(MB) |
|---------|-----|---------|--------|----------|---------|---------|---------|---------|
| 1T | 6,245 | 1.00x | 98.30% | 0.16 | 0.16 | 0.20 | 0.21 | 726 |
| 2T | 9,985 | 1.60x | 98.30% | 0.20 | 0.19 | 0.32 | 0.37 | 728 |
| 4T | 18,496 | 2.96x | 98.30% | 0.21 | 0.18 | 0.34 | 0.37 | 732 |
| 8T | 28,344 | 4.54x | 98.30% | 0.27 | 0.25 | 0.45 | 0.51 | 740 |
| 12T | 30,496 | 4.88x | 98.30% | 0.37 | 0.33 | 0.59 | 0.65 | 747 |
| **16T** | **40,358** | **6.46x (peak)** | 98.30% | 0.36 | 0.34 | 0.53 | 0.58 | 755 |
| 24T | 37,555 | 6.01x (回退) | 98.30% | 0.57 | 0.58 | 0.71 | 0.98 | 770 |

## hnswlib Native DEEP10M (unlimited memory)

| Threads | QPS | Scaling | Recall | Mean(ms) | P50(ms) | P95(ms) | P99(ms) | RSS(MB) |
|---------|-----|---------|--------|----------|---------|---------|---------|---------|
| 1T | 1,806 | 1.00x | 95.12% | 0.55 | 0.56 | 0.71 | 0.80 | 5,967 |
| 2T | 3,822 | 2.12x | 95.12% | 0.52 | 0.53 | 0.67 | 0.75 | 5,986 |
| 4T | 7,226 | 4.00x | 95.12% | 0.55 | 0.57 | 0.69 | 0.77 | 6,024 |
| 8T | 11,523 | 6.38x | 95.12% | 0.69 | 0.69 | 0.97 | 1.24 | 6,100 |
| **12T** | **12,480** | **6.91x (peak)** | 95.12% | 0.96 | 0.89 | 1.56 | 1.74 | 6,177 |

## 三方对比

### SIFT1M: DiskHNSW (512MB cgroup) vs hnswlib (512MB cgroup) vs hnswlib (unlimited)

| Threads | DiskHNSW 512MB | hnswlib 512MB | hnswlib unlimited | DiskHNSW vs unlimited |
|---------|---------------|--------------|-------------------|----------------------|
| 1T | 2,744 | 51 | 6,245 | 0.44x |
| 4T | 9,657 | 214 | 18,496 | 0.52x |
| 12T | 17,610 | 496 | 30,496 | 0.58x |
| 16T | 18,044 | 648 | 40,358 | 0.45x |
| 24T | 17,288 | 731 | 37,555 | 0.46x |

### DEEP10M: DiskHNSW (2GB cgroup) vs hnswlib (unlimited)

| Threads | DiskHNSW 2GB | hnswlib unlimited | DiskHNSW vs unlimited | DiskHNSW 内存节省 |
|---------|-------------|-------------------|----------------------|------------------|
| 1T | 302 | 1,806 | 0.17x | 4.2x (1.4GB vs 6.0GB) |
| 2T | 572 | 3,822 | 0.15x | 4.1x |
| 4T | 779 | 7,226 | 0.11x | 4.1x |
| 8T | 678 | 11,523 | 0.06x | 4.0x |
| 12T | 634 | 12,480 | 0.05x | 3.9x |

## 分析

### SIFT1M 对比
- DiskHNSW 1T QPS = hnswlib unlimited 的 **44%**（用 27% 的内存：197MB vs 726MB）
- 4T 是最佳效率点：DiskHNSW = hnswlib 的 **52%**，内存仅 28%
- recall 差 2.5pp（95.80% vs 98.30%），这是 PQ 近似的预期代价

### DEEP10M 对比
- DiskHNSW 4T QPS = hnswlib 的 **11%**，但内存仅 **24%**（1.5GB vs 6.0GB）
- 8T+ 回退后差距拉大（6%），说明 I/O 瓶颈严重
- recall 差 0.27pp（94.85% vs 95.12%），非常接近

### Scaling 特性对比

| 系统 | SIFT1M 峰值 | DEEP10M 峰值 | SIFT1M 线性区间 | DEEP10M 线性区间 |
|------|------------|-------------|----------------|-----------------|
| DiskHNSW (cgroup) | 16T: 18K | 4T: 779 | 1-4T | 1-2T |
| hnswlib (unlimited) | 16T: 40K | 12T: 12.5K | 1-4T | 1-4T |
| hnswlib (512MB) | - | N/A (OOM) | - | - |

### 关键洞察
1. **内存是 scaling 的硬约束**：hnswlib 在 512MB cgroup 下 QPS 暴跌 100x+，在 unlimited 下正常
2. **DiskHNSW 的价值定位**：不是比 hnswlib 快，而是用 1/4 内存达到 1/2 的 QPS（SIFT1M）
3. **DEEP10M 的差距更大**：I/O 密集 + 内存挤压使 DiskHNSW 效率下降
4. **三者 peak 线程数接近**（12-16T），说明 CPU 拓扑是最终天花板
