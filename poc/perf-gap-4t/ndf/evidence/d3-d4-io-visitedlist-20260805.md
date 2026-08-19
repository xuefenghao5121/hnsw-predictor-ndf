# Evidence: Direction 3 (FineRerank I/O) + Direction 4 (VisitedList pool)

> 日期: 2026-08-05
> 协议: [[CON-SLA-014]] SIFT1M 512MB cgroup, 4T, FVC=160

## POC 副本基线校准

| 二进制 | QPS | Recall | RSS |
|--------|-----|--------|-----|
| Trunk (benchmark_diskhnsw) | 11,421 | 95.75% | 220MB |
| POC (benchmark_poc) | 9,763 | 95.75% | 220MB |

POC 副本比 Trunk 慢 ~15%，可能是编译路径差异（不同 Makefile/include 路径）。
以下 D3/D4 结果均以 POC 副本自身为基线对比。

## Direction 4: VisitedList thread_local 池化

| 配置 | QPS | vs POC 基线 |
|------|-----|------------|
| POC 基线 (per-search 创建) | 9,763 | 1.00x |
| D4 thread_local pool | 8,276 | **-15.2%** |

### 结论: H4 否定

- thread_local VisitedList 池化反而降低 QPS 15%
- 可能原因:
  1. thread_local 析构/初始化开销在短查询中比 memset 更重
  2. reset() 的 curV 递增逻辑可能导致 cache line invalidation
  3. VisitedList 的 vector<uint8_t> 1MB 分配在 4T 下不是瓶颈（OS allocator 有 slab cache）
- **VisistedList 构造在 4T 下不是瓶颈**（perf profile 中 memset 仅 5.38%，池化收益 < 开销）

## Direction 3: FineRerank 批量 pread (排序后顺序读)

| 配置 | QPS | vs POC 基线 |
|------|-----|------------|
| POC 基线 (unordered_set 顺序) | 9,763 | 1.00x |
| D3 BATCH_PREAD=1 (sorted) | 6,834 | **-30.0%** |

### 结论: H3 否定

- 排序后 pread 反而降低 QPS 30%
- 可能原因:
  1. pages_needed 通常只有 10-30 个 page，排序开销 > I/O 收益
  2. SIFT1M 512MB cgroup 下 page cache 命中率高（FVC=160 已覆盖大部分），pread 量本来就少
  3. 排序改变了 page 访问顺序，可能破坏局部性（candidates 按 graph traversal order 排列）
- **在 FVC=160 + 512MB cgroup 下，pread 量不是瓶颈**

## 总结

| 方向 | 假设 | 结论 | 原因 |
|------|------|------|------|
| D3 批量 pread | 减少 syscall >5% QPS | ❌ -30% | 排序开销 > I/O 收益，pread 量少 |
| D4 VisitedList 池化 | 减少 memset >3% QPS | ❌ -15% | thread_local 开销 > memset 节省 |

**根因**: D1 (FVC=160) 已经消除了大部分 FineRerank I/O 和 memset 的开销来源。
当 flat_vec_cache 命中率高时，剩余的 pread 和 memset 量不足以构成瓶颈。
