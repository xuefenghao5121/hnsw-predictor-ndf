# Behavior — Fine Rerank / Page Search

> 条款索引: `BEH-007`, `BEH-011`, `BEH-014`, `BEH-014-L2`, `BEH-017`（deprecated）

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


## Read Coalescing 行为 (已废弃) {#BEH-017}
<!-- ndf: kind=req level=may layer=L1 status=deprecated since=0.6 source=deduced -->
<!-- ndf: refines=BEH-001 depends-on=DEC-060,API-009 -->

> **Deprecated (2026-07-31):** v1 (pread 路径) 实测 +6-9% QPS，v2 (io_uring 路径) 实测 -10~16% QPS。
> 代码已回退，环境变量 `READ_COALESCE` 不再生效。本条款保留为历史记录。
> 根因：io_uring 批量并行提交已高效处理 4KB 随机读，合并读取引入冗余 I/O 反而退化。
> 详细分析见 [[DEC-061]]。

当 `READ_COALESCE=1` 时，Fine Rerank 对候选页按所属 block 分组，对密集 block 执行单次
大粒度读取。**v1 (pread) 有小幅正收益，v2 (io_uring) 负收益，代码已全部回退。**

**v1 实测（pread, SIFT1M, 512MB cgroup, O_DIRECT, 1T）**：

| REFINE_EF | Recall | 基线 QPS | Coalesce QPS | 提升 |
|-----------|--------|---------|-------------|------|
| 200 | 97.20% | 60.9 | 66.5 | +9.2% |
| 100 | 95.75% | 110.9 | 118.2 | +6.6% |
| 80 | 94.90% | 133.3 | 141.6 | +6.2% |

**v2 实测（io_uring, SIFT1M, 512MB cgroup, O_DIRECT, 1T）**：

| REFINE_EF | Threshold | Recall | 基线 QPS | Coalesce QPS | 变化 |
|-----------|-----------|--------|---------|-------------|------|
| 100 | 3 | 95.75% | 802.0 | 724.7 | **-9.6%** |
| 100 | 5 | 95.75% | 802.0 | 786.5 | -1.9% |
| 100 | 8 | 95.75% | 802.0 | 783.3 | -2.3% |
| 200 | 3 | 97.20% | 507.3 | 426.1 | **-16.0%** |

> rationale: v1 pread 路径有 +6-9% 收益（syscall 开销减少），但 pread 路径本身比
> io_uring 慢 7x。v2 io_uring 路径负收益根因：io_uring 批量并行提交 100 个 4KB SQE，
> NVMe 并行处理，延迟 ≈ max(单次I/O, 总数据/带宽)。合并 64KB 读取引入冗余数据
> (3 页 12KB 有效 -> 读 64KB)，SQE 减少的收益 < 冗余 I/O 代价。
