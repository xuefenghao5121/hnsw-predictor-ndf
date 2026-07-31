# Proposal: Read Coalescing v2 - io_uring 路径候选页合并读取

> 日期: 2026-07-31
> 关联: DEC-060 方向 1 (★★★), BEH-017 (v1 pread 路径, 已验证收益有限)
> 场景: 场景1 增量特性
> Status: Pending

## 背景

BEH-017 v1 在 pread 路径上实现了 Read Coalescing，实测收益 +6-9%（远低于预期 +30%）。
根因分析：pread 逐页 syscall 开销主导（~2-3μs/call），coalescing 减少了 I/O 次数但未消除
syscall 开销。且 pread 路径本身比 io_uring 慢 2x（60.9 vs 130 QPS @REFINE_EF=200）。

**v1 实测数据（SIFT1M, 512MB cgroup, O_DIRECT, 1T）：**

| REFINE_EF | Recall | 基线 QPS | Coalesce QPS | 提升 |
|-----------|--------|---------|-------------|------|
| 200 | 97.20% | 60.9 | 66.5 | +9.2% |
| 100 | 95.75% | 110.9 | 118.2 | +6.6% |
| 80 | 94.90% | 133.3 | 141.6 | +6.2% |

**结论**：pread 路径不是 I/O 优化的正确着力点。io_uring 路径已有批量提交机制，
将 16× 4KB 提交合并为 1× 64KB 提交，能同时获得 SQE 减少和 I/O 合并的双重收益。

## 当前 io_uring 路径分析

io_uring 路径（`disk_hnsw.cpp:1820-1960`）当前逻辑：

1. 遍历 `pages_needed`（std::set<uint32_t>，已排序）
2. 对每个 page 调用 `submitReadNF(fd, page<<12, 4096, buf, userdata)`
3. 已有 `FINE_MERGE` 优化：相邻两页（p0, p0+1）合并为 8KB 读取
4. `flushSqe()` + `submit()` 一次性提交所有 SQE
5. `waitCompletion()` + `reapCompletions()` 等待全部完成
6. 通过 `page_buf[page]` 映射获取数据指针

**当前 FINE_MERGE 的局限**：
- 只合并相邻 2 页（8KB），不合并同 64KB block 内的非相邻页
- 没有利用 BFS 重排后的 block 级局部性
- 100 个候选 -> ~100 个 SQE，即使 FINE_MERGE 也只能减少到 ~50

## v2 方案：io_uring 路径 Read Coalescing

**核心思路**：在 io_uring 提交前，将 pages_needed 按 64KB block 分组。
对密集 block（≥3 候选页）提交 1 个 64KB 读取请求，替代多个 4KB 请求。

### 实现方案

```
Step 1: 按 block_id 分组
  pages_needed -> block_groups[block_id] = {page1, page2, ...}

Step 2: 对每个 block 组
  if pages.size() >= threshold:
    # 密集 block: 1 个 64KB SQE
    buf = io_ring.allocBuffer()  # 64KB buffer
    file_off = block_id * READ_COALESCE_SIZE
    io_ring.submitReadNF(fd, file_off, READ_COALESCE_SIZE, buf, userdata)
    # userdata 编码: block_id | COALESCE_FLAG
    # 完成后通过 page_buf[page] = buf 指向 64KB buffer 中的对应 4KB 切片
  else:
    # 稀疏 block: 逐页 4KB SQE（保持现有逻辑）
    for page in pages:
      buf = io_ring.allocBuffer()
      io_ring.submitReadNF(fd, page<<12, 4096, buf, userdata)

Step 3: flushSqe() + submit() + waitCompletion()（不变）

Step 4: 完成处理
  对 COALESCE_FLAG 的 CQE:
    big_buf = io_ring.getBuffer(buf_idx)
    for page in block_groups[block_id]:
      page_buf[page] = buf_idx  # getPagePtr 返回 big_buf + (page - base) * 4096
  对普通 CQE:
    page_buf[page] = buf_idx（现有逻辑）
```

### 关键设计决策

1. **buffer 管理**：io_uring 的 buffer pool 需支持 64KB buffer。当前 `allocBuffer()` 分配
   4KB buffer。需要扩展为支持可变大小，或预分配一组 64KB buffer。

2. **page_buf 映射**：当前 `page_buf[page] = buf*2 + half`（8KB 合并编码）。
   v2 需扩展为：`page_buf[page] = buf_idx`（64KB buffer 内偏移通过 `page % 16 * 4096` 计算）。
   统一用 `getPagePtr(page)` lambda 屏蔽差异。

3. **O_DIRECT 对齐**：io_uring buffer pool 已用 `posix_memalign` 对齐，64KB buffer 满足
   O_DIRECT 要求。需确认 `IoUring::allocBuffer` 支持分配 64KB。

4. **userdata 编码**：
   - 4KB 读取：`userdata = page`（现有，32-bit page number）
   - 64KB 读取：`userdata = block_id | (1 << 31)`（高位标记 coalesce）
   - 或用现有 `is8k` 扩展为 `is_coalesce` + `block_id`

5. **与 FINE_MERGE 的关系**：v2 的 64KB 合并是 FINE_MERGE（8KB 合并）的超集。
   当 `READ_COALESCE=1` 时，FINE_MERGE 逻辑被取代（不再逐页检查相邻）。

### 预期收益

| 指标 | v1 (pread) | v2 (io_uring) |
|------|-----------|--------------|
| 基线路径 QPS | 110.9 | ~130 (DEC-057) |
| Coalesce 后 QPS | 118.2 (+6.6%) | ~170-200 (预期 +30-50%) |
| SQE 提交数 | N/A | 100 -> ~40-50 |
| syscall 次数 | N/A | 1 次 submit（io_uring 批量） |

io_uring 路径的优势：
- 1 次 `io_uring_enter` 提交全部 SQE（vs pread 的 N 次 syscall）
- 64KB 读取比 4KB 读取对 NVMe 更高效（减少命令开销）
- 减少 CQE 数量（~40 vs ~100），减少 reap 开销

## 拟修改固定目录（确认落地后）

> **现状**：固定目录 [[BEH-017]] / [[BEH-017-L2]] / [[API-009]] / [[CON-SLA-012]]
> **仅覆盖 pread v1**。下文为 v2 确认后的修订草案；Implemented 前 MUST NOT 把
> io_uring 义务或 ≥160 must SLA 写入固定目录。

### BEH-017（拟修订）: 扩展到 io_uring

当 `READ_COALESCE=1` 时：
1. **pread**（`FINE_PREAD=1`）：维持现行 [[BEH-017]]（`refines=BEH-001`）
2. **io_uring**（`FINE_PREAD=0`）：密集 block 提交 1× `READ_COALESCE_SIZE` SQE，稀疏逐页 4KB SQE

### CON-SLA-012（拟修订）— aspirational，测后升 must

| 路径 | 指标 | 建议下限 | 状态 |
|------|------|----------|------|
| pread (v1) | QPS (1T) | ≥ 115 | **已是**现行 must |
| io_uring (v2) | QPS (1T) | ⟨TBD⟩ 候选 ≥ 160 | 实测前保持 tbd，禁止 must |
| 两者 | Recall | ≥ 95% | 不改变候选集 |

### 拟新增 L2：io_uring Read Coalescing 机制

<!-- 落地时签发新 ID（勿与现行 BEH-017-L2 撞车） -->

io_uring 路径实现要点（草案）：

1. **buffer 分配**：`IoUring::allocBuffer()` 需支持 64KB（双池或统一 64KB）
2. **SQE 编码**：4KB 用 page userdata；64KB 用 `block_id | COALESCE_BIT`
3. **page_buf 映射**：统一 `getPagePtr(page)`；64KB 内偏移 `(page - base) * 4096`
4. **buffer 回收**：多 page 共享 64KB buffer 时去重回收
5. **FINE_MERGE 互斥**：`READ_COALESCE=1` 时跳过 FINE_MERGE（v2 为超集）

## 验证计划

1. **编译验证**: `make bench` 通过
2. **功能验证**: `READ_COALESCE=1 FINE_DIRECT=1 FINE_PREAD=0` recall ≥ 95%
3. **性能验证**: O_DIRECT io_uring 模式下 QPS 对比；达标后再写 CON-SLA must
4. **Buffered 模式回归**: `READ_COALESCE=1 FINE_BUFFERED=1` QPS 不退化
5. **pread 路径回归**: `READ_COALESCE=1 FINE_PREAD=1` v1 行为不变

## 影响范围

- **修改文件**: `src/core/disk_hnsw.cpp`（io_uring 路径增加合并逻辑）
- **可能修改**: `include/io_uring_wrapper.h`（buffer pool 支持 64KB）
- **不影响**: Phase A 搜索、BlockCache、数据 pipeline

## 拟 refines / depends-on（落地时）

- 扩展 [[BEH-017]]（仍 `refines=BEH-001`，**禁止** `refines=BEH-007`）
- 修订 [[CON-SLA-012]]（仅在有实测后加入 io_uring 行）
- `depends-on: DEC-060`
