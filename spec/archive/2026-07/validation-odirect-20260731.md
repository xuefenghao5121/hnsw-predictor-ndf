# 性能验证报告: O_DIRECT 诚实基准测试

> 验证日期: 2026-07-31
> 关联提案: proposal-odirect-benchmark.md
> 关联条款: DEC-030, DEC-039, CON-HONEST-002
> 场景: 场景6 (性能验证)

## 测试环境

- 机器: Intel Xeon, 30GB RAM, NVMe SSD
- 数据集: SIFT1M (128D, 1M), DEEP10M (96D, 10M)
- 方法: drop_caches + cgroup v2 MemoryMax
- 每组: 200 queries, 1 轮 (O_DIRECT 模式无需多轮取峰, 无 page cache 预热效果)

## 结果总表

### SIFT1M (128D, 1M, 512MB cgroup)

| 模式 | 线程 | Recall | Mean | QPS | RSS | QPS 差距 |
|------|------|--------|------|-----|-----|---------|
| **A. Buffered** | 1T | 95.70% | 0.41ms | 2450 | 271MB | 基线 |
| **C. O_DIRECT** | 1T | 95.70% | 7.69ms | 130 | 271MB | **-94.7%** |
| **A. Buffered** | 4T | 95.70% | 0.12ms | 8312 | 277MB | 基线 |
| **C. O_DIRECT** | 4T | 95.70% | 1.99ms | 502 | 277MB | **-94.0%** |

### DEEP10M (96D, 10M, 3GB cgroup)

| 模式 | 线程 | Recall | Mean | QPS | RSS | QPS 差距 |
|------|------|--------|------|-----|-----|---------|
| **A. Buffered** | 4T | 95.15% | 0.65ms | 1535 | 2502MB | 基线 |
| **C. O_DIRECT** | 4T | 95.15% | 5.92ms | 169 | 2502MB | **-89.0%** |

### DEEP10M (96D, 10M, 2GB cgroup)

| 模式 | 线程 | Recall | Mean | QPS | RSS |
|------|------|--------|------|-----|-----|
| **C. O_DIRECT** | 4T | 95.15% | 5.87ms | 170 | 1892MB |

## 关键发现

### 1. Page Cache 水分极大

**SIFT1M 1T**: Buffered 2450 QPS -> O_DIRECT 130 QPS (**18.8x 虚高**)
**SIFT1M 4T**: Buffered 8312 QPS -> O_DIRECT 502 QPS (**16.6x 虚高**)
**DEEP10M 4T**: Buffered 1535 QPS -> O_DIRECT 169 QPS (**9.1x 虚高**)

之前报告的 "10x faster than hnswlib" 在 O_DIRECT 下完全不成立:
- hnswlib SIFT1M 全内存: ~11800 QPS
- DiskHNSW O_DIRECT SIFT1M 1T: 130 QPS (90x slower)
- DiskHNSW O_DIRECT SIFT1M 4T: 502 QPS (23x slower)

### 2. Recall 不受影响

所有测试 recall 不变 (95.70% / 95.15%)，确认 I/O 路径不影响算法正确性。

### 3. RSS 不受影响

Buffered 和 O_DIRECT 的 RSS 相同 (271MB / 2502MB)，因为匿名内存 (CSR, PQ codes,
flat_vec_cache) 不变。差异在 file cache: Buffered 模式下 page cache 额外占用
cgroup 内的 file 预算。

### 4. O_DIRECT 延迟分析

SIFT1M O_DIRECT 1T: 7.69ms/query
- 100 候选 × 4KB 页 × NVMe ~50-100μs/读 = 5-10ms (I/O 主导)
- PQ 计算 + 图遍历 ~0.4ms (与 buffered 相同)

DEEP10M O_DIRECT 4T: 5.92ms/query
- 300 候选 × 4KB 页 / 4 线程 = ~75 次 I/O/线程
- NVMe 并发 ~50-100μs/读 = 3.75-7.5ms

### 5. cgroup 2GB vs 3GB 对 O_DIRECT 无影响

DEEP10M O_DIRECT: 2GB 170 QPS vs 3GB 169 QPS (噪声级差异)。
O_DIRECT 不使用 page cache, cgroup 限制主要约束匿名内存, 2GB 已足够。

## 结论

1. **之前所有 Buffered 数字包含 9-19x 的 page cache 水分**
2. **O_DIRECT 下 DiskHNSW 比 hnswlib 慢 23-90x** (不是 10x faster)
3. **DiskHNSW 的核心价值仍然是内存节省** (271MB vs 726MB), 而非速度
4. **100M 规模验证是必要的**: 只有在那个规模 page cache 才完全失效, O_DIRECT 成为必须
5. **io_uring 在 O_DIRECT 下可能有更大优势** (批量提交掩盖 I/O 延迟), 需额外测试
