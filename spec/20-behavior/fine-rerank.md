# Behavior — Fine Rerank / Page Search

> 条款索引: `BEH-007`, `BEH-011`, `BEH-014`, `BEH-014-L2`, `BEH-017`, `BEH-017-L2`

## Fine Rerank 4KB 页计算 {#BEH-007}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-001 -->

Fine Rerank (`disk_hnsw.cpp:1688-1913`) MUST 按以下公式计算 vecblocks 文件偏移：

```
off = 4096 + b * vec_block_size_ + block_data_offset_[b] + node_slot_table_[nid] * dim * sizeof(float)
page0 = off >> 12
oip = off & 4095
cross = (oip + dim * sizeof(float)) > 4096  // 跨页检测
```

关键：MUST 使用 `vec_route_table_[nid]`（而非 `route_table_[nid]`）获取 vecblocks 块号。

## 跨页向量拼接 {#BEH-011}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-007 -->

当向量跨越 4KB 页边界时（`slot % 8 == 6`，SIFT dim=128, data_offset=520），Fine Rerank MUST：
1. 从 page0 读取 `4096 - oip` 字节
2. 从 page1 读取 `dim * sizeof(float) - first` 字节
3. 拼接到临时 buffer `tmp_vec[512]` 或 `tmp_vec_pread[512]`
4. 然后计算精确 L2 距离

## Page Search 行为 {#BEH-014}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.2 source=deduced -->
<!-- ndf: refines=BEH-001 depends-on=DEC-017 -->

当 `PAGE_SEARCH=1` 时，Fine Rerank MUST 在读取每个 4KB 页后，扫描页内所有向量计算精确 L2 距离并插入候选集。

**L1 契约**：
- 页内所有向量 MUST 被计算，而非仅候选向量
- "邻居向量"（同页但非候选）只做距离计算，MUST NOT 入图遍历队列
- MUST 使用 `vec_slot_to_node_[block][slot]` 反向映射定位页内向量
- 环境变量 `PAGE_SEARCH=0`（默认）时 MUST 完全跳过此行为，零额外开销

> 当前状态: recall +0.5pp (96.20%), QPS -11% (1832). 降级为实验性 SHOULD, 见 [[DEC-020]] [[CON-SLA-008]].

### Page Search 扫描实现 {#BEH-014-L2}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.2 source=observed -->
<!-- ndf: refines=BEH-014 -->

`pageSearchScan(pg, page_data, page_len)` 在 `disk_hnsw.cpp:1757` 中定义，MUST 按以下步骤扫描页内所有向量：

1. **页位置计算** (`disk_hnsw.cpp:1759-1772`):
   - 从页号 `pg` 计算文件字节偏移 `pg_off = pg << 12`
   - 排除 4096B 文件头区域（`pg_off < 4096` 直接返回）
   - 计算所属 vecblock: `b = (pg_off - 4096) / vec_block_size_`
   - 计算向量区起始: `blk_start = 4096 + b * vec_block_size_ + block_data_offset_[b]`
   - 计算首个向量 slot: `first_slot = (pg_off - blk_start) / slot_size`
   - 计算页内 slot 数: `slots_in_page = page_len / slot_size`
   - 其中 `slot_size = dim * sizeof(float)` (SIFT=512B)

2. **Slot 遍历** (`disk_hnsw.cpp:1773-1782`):
   ```cpp
   for (uint32_t s = first_slot; s < first_slot + slots_in_page && s < max_slot; s++) {
       uint32_t nid = vec_slot_to_node_[b][s];   // DEC-017: slot→node 反向映射
       if (page_considered.count(nid)) continue;  // 去重 (候选可能已计算)
       const float* vec = reinterpret_cast<const float*>(page_data + byte_off);
       consider(nid, vec);                         // 计算 L2 + 插入 refined 候选集
       cache_->putFlatVector(nid, vec);           // 回填热向量 cache
       ps_extra_considered++;
   }
   ```

3. **去重机制** (`disk_hnsw.cpp:1745-1752`):
   - 全局 `std::unordered_set<uint32_t> page_considered`
   - `consider()` lambda 内部检查 `page_considered.count(nid)`，避免重复计算
   - 候选向量已在进入 Page Search 前通过 `consider()` 计算，其 node_id 已标记

4. **反向映射构建** (`disk_hnsw.cpp:2206,2225`):
   - `buildFineRerank()` 中新增 `vec_slot_to_node_.resize(num_blocks)`，然后逐 block 存入 `ids[0..cnt-1]`
   - 索引语义: `vec_slot_to_node_[b][slot] = node_id`，O(1) 访问

5. **调用点**:
   - **pread 路径** (`disk_hnsw.cpp:1828-1833`): 每页 pread 完成后立即 `pageSearchScan(pg, buf.get(), 4096)`
   - **io_uring 路径** (`disk_hnsw.cpp:1965-1971`): 对去重页集 `scanned_pages` 逐一调用 `pageSearchScan`

6. **统计输出** (`disk_hnsw.cpp:2007-2009`):
   - `PROFILE_FINE=1` 时额外输出 `ps_extra` (每 query 额外考虑向量数) 和 `ps_hits` (命中 top-K 数)


## Read Coalescing 行为 {#BEH-017}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.6 source=deduced -->
<!-- ndf: refines=BEH-001 depends-on=DEC-060,API-009 -->

当 `READ_COALESCE=1` **且** `FINE_PREAD=1` 时，Fine Rerank MUST 对候选页按所属
block（大小 = `READ_COALESCE_SIZE`）分组，对密集 block（候选页数 ≥
`READ_COALESCE_THRESHOLD`，默认 3）执行单次大粒度读取，替代多次 4KB 读取。

**适用范围（v1 SoT）**：仅 **pread 路径**（`FINE_PREAD=1`）。
`FINE_PREAD=0`（io_uring）下的合并读取 **不在本条款义务内**；见 Pending 提案
`spec/open/proposal-read-coalescing-v2.md`。

**L1 契约**：
1. 候选页 MUST 按 `block_id = page / (READ_COALESCE_SIZE / 4096)` 分组
2. 同 block 内候选页数 ≥ `READ_COALESCE_THRESHOLD` 时，MUST 一次读取 `READ_COALESCE_SIZE` 字节
3. 同 block 内候选页数 < threshold 时，MUST 保持逐页 4KB 读取（不合并）
4. 合并读入的数据 MUST 对后续精排逻辑等价于逐页 4KB 读（跨页拼接 [[BEH-011]]、
   Page Search [[BEH-014]] MUST NOT 被破坏）
5. `READ_COALESCE=0`（默认）时 MUST 走原有逐页路径，行为与未引入本特性前一致
6. 不得因合并读取改变候选集合或 Recall 语义

### Read Coalescing pread 机制 {#BEH-017-L2}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.6 source=observed -->
<!-- ndf: refines=BEH-017 -->

pread 路径实现（`disk_hnsw.cpp`）：密集 block 用 `posix_memalign` 分配对齐 buffer 后
一次 `pread(READ_COALESCE_SIZE)`，再按 4KB 切分写入 `page_cache[pg]`；稀疏 block 与
`READ_COALESCE=0` 仍逐页 4KB `pread`。

**v1 实测（pread, SIFT1M, 512MB cgroup, O_DIRECT, 1T）**：

| REFINE_EF | Recall | 基线 QPS | Coalesce QPS | 提升 |
|-----------|--------|---------|-------------|------|
| 200 | 97.20% | 60.9 | 66.5 | +9.2% |
| 100 | 95.75% | 110.9 | 118.2 | +6.6% |
| 80 | 94.90% | 133.3 | 141.6 | +6.2% |

> rationale: pread 路径收益 +6–9%，低于 DEC-060 方向1 初估 +30%；根因是逐页
> syscall 开销仍占主导。抬升地板的下一刀在 io_uring 批量合并（v2 提案），不抬高本条款。
