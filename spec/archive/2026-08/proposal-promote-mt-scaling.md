# Proposal: Promote multi-thread-scaling A2+C2

> track: promote
> 日期: 2026-08-05
> Status: Implemented on 2026-08-05
> Promotes: multi-thread-scaling
> 关联: [[CHR-006]]、[[CON-SLA-014]]、[[CON-SLA-016]]、[[BEH-024]]、[[BEH-018]]、[[BEH-019]]、[[BEH-025]]、[[DEC-070]]、[[DEC-073]]
> POC 证据: `poc/multi-thread-scaling/ndf/TOPIC.md`

## 1. 变更概述

### A2: WILLNEED 无锁后台线程 (代码变更)

将 `posix_fadvise(WILLNEED)` 从搜索线程移到后台 I/O 线程，消除多线程内核锁竞争。
使用 SPSC per-thread slot + atomic flag，零 mutex 竞争。

- 环境变量: `WILLNEED_BG=1` (opt-in, 默认关闭)
- 文件: `src/core/disk_hnsw.cpp` searchKnn FineRerank 段
- 预期: 12T +50%, 16T +73%, 256MB 12T +61%

### C2: 自适应 VisitedList 池化 (代码变更)

高并发 (T≥阈值) 时复用 thread_local VisitedList，消除 1MB memset 的 cache bouncing。
低并发走原始路径，零退化。

- 环境变量: `VL_POOL_THREADS=N` (默认 999=不启用, 推荐 14)
- 文件: `src/core/disk_hnsw.cpp` searchKnn
- 预期: 16T+ 额外 +6~13% (与 A2 叠加)

### 新增 SLA: CON-SLA-017

512MB cgroup + A2+C2 优化下的性能下限。

### 新增 DEC-074

WILLNEED 后台线程化 + VisitedList 池化决策记录。

## 2. draft → stable ID 清单

| ID | 变更 | 类型 |
|----|------|------|
| `BEH-027` | 新增: WILLNEED 后台线程化行为 | new stable |
| `API-013` | 新增: WILLNEED_BG / VL_POOL_THREADS 环境变量 | new stable |
| `CON-SLA-017` | 新增: SIFT1M 512MB A2+C2 SLA | new stable |
| `DEC-074` | 新增: 多线程优化决策 | new stable |

## 3. src/ 改动概述

### disk_hnsw.cpp - searchKnn FineRerank 段

**A2 改动** (WILLNEED_BG=1):
```cpp
// 旧: 搜索线程直接调用 posix_fadvise (多线程内核锁竞争)
for (uint32_t pg : pages_needed) {
    posix_fadvise(vec_blocks_fd_, (off_t)pg << 12, 4096, POSIX_FADV_WILLNEED);
}
// 新: SPSC slot + 后台线程 (零 mutex)
static struct BgSlot { atomic<bool> ready; vector<uint32_t> pages; } bg_slots[128];
static thread bg_thread(polling all slots, fadvise each);
// 搜索线程: write to own slot -> set ready flag
```

**C2 改动** (VL_POOL_THREADS>=N):
```cpp
// 旧: 每次 searchKnn 创建 VisitedList (1MB memset)
VisitedList visited(graph_.num_nodes);
// 新: T>=阈值时复用 thread_local VisitedList
static thread_local unique_ptr<VisitedList> tl_vl_pool;
if (num_threads >= vl_pool_threshold) { reset() reuse } else { original path }
```

## 4. 证据摘要 (comprehensive sweep, 13 thread counts)

### 512MB peak: 30,332 QPS (16T) = hnswlib 的 73.3%

| 配置 | 1T | 4T | 8T | 12T | 16T (peak) | 24T |
|------|-----|-----|------|------|-----------|------|
| baseline | 3,147 | 10,723 | 14,224 | 17,207 | 18,317 | 19,766 |
| A2+C2 | 3,133 | 9,041 | 14,901 | 18,459 | **30,332** | 29,738 |
| hnswlib | 6,293 | 14,476 | 32,041 | 38,907 | 39,322 | 39,289 |

### 256MB peak: 16,873 QPS (16T) = hnswlib 的 42.9%

### QPS/MB 内存效率

| 配置 | Peak QPS | 内存 | QPS/MB | vs hnswlib |
|------|---------|------|--------|-----------|
| DiskHNSW 256MB | 16,873 | 256MB | 65.9 | **1.17x** |
| DiskHNSW 512MB | 30,332 | 512MB | 59.2 | **1.05x** |
| hnswlib | 41,370 | 732MB | 56.5 | 1.0x |

## 5. 语义核决策 ([[META-004]] / [[BEH-019]] §6)

**决策: 不要**

理由: 本次 promote 是 I/O 调度优化 (WILLNEED 后台线程化) + 内存复用 (VisitedList 池化)，
不涉及新搜索行为或新接口语义。现有 L1 [[BEH-024]] (L4 cache 管理) 已覆盖 WILLNEED 语义。
新增 [[BEH-027]] 扩展为后台线程行为，VER 验证通过即可。

## 6. 不做的事

- 不 promote B (WILLNEED disable) -- 窗口太窄
- 不 promote A3 (page merge) -- 512MB 16T+ 有害
- 不改 WILLNEED / REFINE_EF / PQ M 默认值
- 不改 CON-SLA-014 协议
