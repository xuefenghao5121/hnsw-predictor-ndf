# Behavior — I/O 模式与实验特性

> 条款索引: `BEH-015`, `BEH-015-L2`, `BEH-016`

## Dynamic Width 行为 {#BEH-015}
<!-- ndf: kind=req level=may layer=L1 status=deprecated since=0.2 source=deduced -->
<!-- ndf: refines=BEH-001 depends-on=DEC-019,DEC-024 -->

> **Deprecated:** [[DEC-024]] 正式放弃 Dynamic Width（PQ 粗筛不收敛为架构特性）。
> 代码默认 `DYNAMIC_WIDTH=0`，保留实现供实验，不纳入 SLA。

当 `DYNAMIC_WIDTH=1` 时，Phase A 搜索 MUST 使用自适应 efSearch 宽度：搜索初期使用全宽度，候选集收敛后逐步收窄。

**L1 契约**（历史；现行默认关闭）：
- 收敛检测: 连续 `DW_CONVERGE_HOP` 跳 top-K 无变化时触发收窄
- 收窄策略: efSearch 按几何衰减 `× DW_DECAY`，下限 `EF_SEARCH_MIN`
- `DYNAMIC_WIDTH=0`（默认）时 MUST 使用固定 efSearch，行为与基线完全一致
- 收窄后 MUST 更新 lowerBound 并裁剪 top_candidates

> 当前状态: 实现完成但性能验证无效果；已 deprecated。

### Dynamic Width 收敛检测实现 {#BEH-015-L2}
<!-- ndf: kind=req level=may layer=L2 status=deprecated since=0.2 source=observed -->
<!-- ndf: refines=BEH-015 -->

收敛检测与宽度衰减在 `searchLayer0()` 的 while 循环末尾 (`disk_hnsw.cpp:826-848`) 执行：

1. **参数配置** (`disk_hnsw.cpp:447-453`):
   - `DYNAMIC_WIDTH=1` 开启（默认 0 关闭）
   - `DW_CONVERGE_HOP` 收敛跳数（默认 10）
   - `DW_DECAY` 衰减率（默认 0.75，几何衰减）
   - `EF_SEARCH_MIN` 最小 efSearch（默认 32）

2. **状态变量** (`disk_hnsw.cpp:454-457`):
   ```cpp
   size_t dw_effective_ef = current_ef;   // 当前有效宽度，初值=传入的 ef
   size_t dw_converge_count = 0;          // 连续无变化计次
   uint64_t dw_prev_topk_hash = 0;        // 上一轮 top_candidates 签名
   ```

3. **变化检测** (`disk_hnsw.cpp:829-833`):
   - 对 `top_candidates` 做快照拷贝 `tc_copy`
   - 取前 3 个元素的 `node_id` 做 XOR hash: `hash ^= (uint64_t)node_id << (h * 21)`
   - 与 `dw_prev_topk_hash` 比较：相同则 `dw_converge_count++`，不同则重置为 0

4. **宽度衰减** (`disk_hnsw.cpp:836-844`):
   ```cpp
   if (dw_converge_count >= kDwConvergeHop) {
       size_t new_ef = max(kEfSearchMin, dw_effective_ef * kDwDecay);
       while (top_candidates.size() > new_ef) top_candidates.pop();  // 裁剪
       if (!top_candidates.empty()) lowerBound = top_candidates.top().first;  // 更新
       dw_effective_ef = new_ef;
       dw_converge_count = 0;  // 重置计数等待下次收敛
   }
   ```

5. **生效机制**:
   - 裁剪 `top_candidates` 后 `lowerBound` 自动收紧
   - 下一轮 `candidateDist > lowerBound` 条件更严格，自然过滤弱候选
   - 不做 `ef` 全量 text 替换——仅通过外部裁剪 + lowerBound 传导实现选择性增强

6. **适用 scope**: 当前仅在 `searchLayer0()` 中生效（TwoStage 路径调用）。其他变体（Beam/NonBlock/BatchIO）暂未集成。
   - 入口: `searchKnn()` → `kTwoStage` 分支 → `searchLayer0(entryNewId, query, ef_coarse, visited)` → 收敛检测在 while 末尾
   - 不适用: `searchLayer0Beam/NonBlocking/BatchIO` 的直接调用路径


## Page Cache 驱逐行为 {#BEH-016}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.3 source=deduced -->
<!-- ndf: refines=BEH-001 depends-on=DEC-021 -->

当 `EVICT_PAGE_CACHE=1` 时，DiskHNSW MUST 在每次 `searchKnn()` 返回前对 vecblocks 文件
调用 `posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED)`，驱逐整个文件的 page cache。

**L1 契约**：
- 驱逐目标: 仅 vecblocks fd，MUST NOT 驱逐 blocks_64k（BlockCache 自管理）
- 时机: 每次查询完成后（return result 前）
- `EVICT_PAGE_CACHE=0`（默认）时 MUST 零开销
- 驱逐后下一查询的 Fine Rerank 读取走真实磁盘 I/O

> 实测: 热态 2083 QPS -> 冷态 842 QPS（-60%），I/O 占比 ~60%。
> 冷态 SLA: QPS ≥ 500（见 [[CON-SLA-010]]）。
