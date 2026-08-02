# Decisions - 内存优化 Promote (DEC-064)

> 条款索引: `DEC-064`
> 关联: `DEC-063`、`DEC-034`、`CHR-006`、`CON-002`、`BEH-019`

## D-064: Promote 内存优化 - VisitedList uint8 + adjacency0 streaming free + malloc_trim {#DEC-064}
<!-- ndf: kind=decision date=2026-08-02 affects=CON-002,DEC-034 source=observed -->
<!-- ndf: depends-on=DEC-063,BEH-019 -->

**Context.** POC io-pipelining 期间发现内存优化（VisitedList uint8 + adjacency0 streaming free + malloc_trim）
对 DEEP10M 性能有 5.5x 提升，远超 pipe_ring_ 本身的收益。根因：释放 ~1GB RSS 给 page cache，
覆盖更多热集，减少 I/O。内存优化是 POC 探索的副产品，但属于通用机制优化，应 promote 到 Trunk。

### 变更内容

1. **VisitedList uint32_t -> uint8_t** (`include/disk_hnsw.h`)
   - 10M 节点：40MB -> 10MB per VisitedList
   - 多线程下每线程独立，4T 省 120MB
   - curV 在 255 次查询后溢出触发 reset，开销可忽略（~20ms / 10000 query）

2. **adjacency0 streaming free** (`src/core/disk_hnsw.cpp` `buildInMemoryAdjacency()`)
   - 构建 bfs_adj 时逐节点 `clear() + shrink_to_fit()` adjacency0[old_id]
   - 峰值内存降低 ~834MB（adjacency0 不再与 bfs_adj + CSR compact 同时驻留）

3. **malloc_trim(0)** (`src/core/disk_hnsw.cpp`)
   - `buildInMemoryAdjacency()` 末尾：归还 CSR 构建释放的 ~1GB 给 OS
   - `loadPQCodes()` 中 upper_vectors 释放后：归还 ~228MB 给 OS

4. **upper_vectors swap** (`src/core/disk_hnsw.cpp` `loadPQCodes()`)
   - `clear()` -> `std::unordered_map<...>().swap()`：确保内存释放而非保留在 allocator 池

### 验证证据

**DEEP10M (10M/96D), EVICT_PAGE_CACHE=1, 10000 queries, REFINE_EF=300, k=10**

| 指标 | pre-fix (DEC-063) | post-fix (本决策) | 变化 |
|------|-------------------|-------------------|------|
| 1T QPS | 106.4 | 581.1 | **+446%** |
| 4T QPS | 180.3 | 1646.5 | **+813%** |
| 4T scaling | 1.69x | 2.83x | +68% |
| RSS | 2422MB | 1634MB | -33% |
| cgroup 下限 | 5GB | 3GB | -40% |
| Recall | 94.85% | 94.85% | 不变 |

**SIFT1M**：512MB cgroup 下性能不受影响（CHR-006 SLA 合规）。

**pipe_ring_ (BEH-021)**：post-fix 后无收益（R1 ≈ R0），保持 draft。内存优化使 page cache
预算充足，pipe_ring_ 预取变成纯开销。待 100M 规模验证。

**Decision.**

1. **Promote 4 处变更到 Trunk `src/`**
2. **DEC-063 amended**：pipe_ring_ 的 DEEP10M 正结果（+162.6%）是 pre-memory-optimization 数据；
   post-fix 后 pipe_ring_ 无收益。DEC-063 的 SIFT1M 负结果仍然有效。
3. **BEH-021 保持 draft**：不 deprecated，100M 规模下 page cache 不足时可能仍有价值
4. **CHR-006 / CON-SLA-011 stable 数字不变**：本优化不改变 SLA 承诺，只提升实际性能

**Alternatives rejected.**
- 同时 promote pipe_ring_：post-fix 数据不支持，BEH-021 保持 draft
- 关闭 pipe_ring_ (deprecated)：100M 规模未验证，过早下结论
- 只 promote 部分：4 处变更协同作用，单独 promote 收益不完整

> rationale: POC 探索的副产品（内存优化）比主目标（pipe_ring_）更有价值，这是探索轨的
> 正常产出。DEC-060 方向 2 的价值在于发现了内存优化的机会，即使 pipe_ring_ 本身暂无收益。
