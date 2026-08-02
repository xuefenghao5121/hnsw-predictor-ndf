# Proposal: Promote 内存优化 - VisitedList uint8 + adjacency0 streaming free + malloc_trim

> track: promote
> 关联: [[DEC-063]]、[[DEC-034]]、[[CHR-006]]、[[CON-002]]、[[BEH-018]]、[[BEH-019]]
> 日期: 2026-08-02
> Status: Implemented on 2026-08-02
> POC 验证: DEEP10M 1T 106.4 -> 581.1 QPS (5.5x), 4T 180.3 -> 1646.5 QPS (9.1x)
> 决策: [[DEC-064]]

## 1. 变更清单

从 `poc/io-pipelining/` 合入 `src/` 的 4 处变更：

### 1.1 VisitedList uint32_t -> uint8_t

**文件**: `include/disk_hnsw.h`

```diff
 struct VisitedList {
-    std::vector<uint32_t> mass;
-    uint32_t curV;
+    std::vector<uint8_t> mass;
+    uint8_t curV;
```

**收益**: 10M 节点下每个 VisitedList 从 40MB -> 10MB（省 30MB）。
多线程下每线程独立 VisitedList，4T 省 120MB。

**风险**: uint8_t curV 在 255 次查询后溢出触发 reset（全量 fill）。
多线程下每线程独立 VisitedList，不影响正确性。benchmark 内 10000 query 会触发 ~39 次 reset，
每次 fill 10MB 约 0.5ms，总开销 ~20ms，可忽略。

### 1.2 adjacency0 streaming free

**文件**: `src/core/disk_hnsw.cpp` `buildInMemoryAdjacency()`

```diff
 for (uint32_t old_id = 0; old_id < N; old_id++) {
     uint32_t new_id = old_to_new_[old_id];
     bfs_adj[new_id].reserve(graph_.adjacency0[old_id].size());
     for (uint32_t old_neighbor : graph_.adjacency0[old_id]) {
         bfs_adj[new_id].push_back(old_to_new_[old_neighbor]);
     }
     std::sort(bfs_adj[new_id].begin(), bfs_adj[new_id].end());
+    // 逐节点释放，降低峰值内存 ~834MB
+    graph_.adjacency0[old_id].clear();
+    graph_.adjacency0[old_id].shrink_to_fit();
 }
+graph_.adjacency0.clear();
+graph_.adjacency0.shrink_to_fit();
```

**收益**: 原始 adjacency0 (834MB) 在循环中逐节点释放，避免与 bfs_adj + CSR compact 同时驻留。
峰值内存降低 ~834MB。

### 1.3 malloc_trim(0) after CSR construction

**文件**: `src/core/disk_hnsw.cpp` `buildInMemoryAdjacency()` 末尾

```diff
 bfs_adj.clear();
 bfs_adj.shrink_to_fit();
+malloc_trim(0);
```

**收益**: 强制归还释放的内存给 OS，降低 RSS ~1GB。
cgroup memory.max 不会因残留 RSS 误触发 OOM。

### 1.4 upper_vectors swap + malloc_trim

**文件**: `src/core/disk_hnsw.cpp` `loadPQCodes()`

```diff
-graph_.upper_vectors.clear();
+std::unordered_map<uint32_t, std::vector<float>>().swap(graph_.upper_vectors);
+malloc_trim(0);
```

**收益**: `clear()` 不保证归还内存；`swap()` 确保释放。+ `malloc_trim` 归还 OS。
DEEP10M: 释放 228MB upper_vectors 后立即归还。

## 2. 需要新增的 include

```diff
+#include <malloc.h>
```

## 3. 验证证据

### DEEP10M (10M/96D), EVICT_PAGE_CACHE=1, 10000 queries, REFINE_EF=300

| 配置 | cgroup | 1T QPS | 4T QPS | 4T scaling | Recall | RSS |
|------|--------|--------|--------|------------|--------|-----|
| pre-fix (DEC-063) | 5GB | 106.4 | 180.3 | 1.69x | 94.85% | 2422MB |
| post-fix (本提案) | 5GB | 581.1 | 1646.5 | 2.83x | 94.85% | 1634MB |
| post-fix | 3GB | 582.1 | - | - | 94.85% | 1634MB |

- **1T QPS**: 106.4 -> 581.1 (+446%)
- **4T QPS**: 180.3 -> 1646.5 (+813%)
- **4T scaling**: 1.69x -> 2.83x
- **RSS**: 2422MB -> 1634MB (-33%)
- **cgroup 下限**: 5GB -> 3GB

### SIFT1M (1M/128D), 512MB cgroup (已验证不影响)

SIFT1M 规模下 VisitedList 省 3MB，adjacency0 streaming free 省 ~20MB。
CHR-006 SLA 不受影响（SIFT1M 数字在 POC binary 中已验证一致）。

## 4. 不做的事

- 不 promote pipe_ring_（BEH-021 保持 draft）
- 不改 stable SLA 数字（CHR-006 / CON-SLA-011 保持）
- 不改 L0/L1 条款（纯 L2 机制优化）

## 5. 对齐条款

- [[CHR-006]] 关键性能承诺 - 不改数字，但提升实际性能
- [[CON-002]] 内存与缓存限制 - 降低 RSS，更充分利用 cgroup 预算
- [[DEC-034]] PQ codes for upper layer - 配合 upper_vectors 释放优化
- [[BEH-019]] 晋升闸门 - 有 POC 证据 + 编译验证 + 性能验证
