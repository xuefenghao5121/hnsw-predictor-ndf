# Behavior — BlockCache

> 条款索引: `BEH-009`, `BEH-009-L2`, `BEH-010`

## Block 解析分支 {#BEH-009}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->
<!-- ndf: depends-on=API-004 -->

`BlockCache::parseBlock()` (`block_cache.cpp:395-557`) MUST 按下列 **L1 判定契约** 分支
（原 CONFLICT-001 提升；布局见 [[API-004]]）：

1. **VecOnly 判定（先于标准头）**：按 VecOnlyHeader 在 offset 12 读取 `flags:u32`；
   若 `(flags & FLAG_VEC_ONLY) != 0`，则 MUST 按 Vec-only 格式解析
   （16B header + node_ids + vectors，无邻接表）。
2. **标准 / PQ 格式（VecOnly 未置位后）**：
   - **PQ 模式**（`data_offset == 0`）：BlockHeader + node_ids + adj_lists，无向量
   - **标准格式**（`data_offset > 0`）：
     - 压缩格式（`FLAG_NEIGHBOR_DELTA_VARINT`）：解码 delta+varint 邻居
     - 原始格式：uint32 数组邻居

> rationale: 标准 BlockHeader 的 `flags:u8` 位于 offset 16；若误用 offset 12 的
> `adj_offset` 低位检测 `FLAG_VEC_ONLY`，存在把普通块误判为 VecOnly 的理论风险。
> 现行实现以 VecOnlyHeader 语义做先检后解析；长期 MAY 引入独立 magic 进一步硬化。

### Block 解析机制 {#BEH-009-L2}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-009 -->

机制细节（observed）：`parseBlock()` 先 `memcpy` offset 12 的 u32 做 VecOnly 检测，
未命中再按 24B BlockHeader 继续解析邻接/向量区。

## 缓存替换状态转移 {#BEH-010}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-001 -->

BlockCache MUST 在缓存满时通过以下流程淘汰：

```
getBlockByNodeId / getBlockById:
  lock(mutex_)
  if cache_map_.find(block_id) != end:
    stats_.cache_hits++
    policy_->onAccess(block_id)
    标记 was_accessed (预取准确率)
    return &block
  else:
    stats_.cache_misses++
    while cache_map_.size() >= cache_slots_:
      victim = policy_->selectVictim()
      if victim == UINT32_MAX: break
      结算预取准确率 (was_prefetched → useful/wasted)
      cache_map_.erase(victim)
      policy_->onRemove(victim)
      invalidateFlatBlockCache(victim)
      stats_.evictions++
    loadBlockFromDisk(block_id)
    parseBlock(block)
    cache_map_.emplace(block_id, block)
    policy_->onInsert(block_id)
    populateFlatCache(block)
    return &block
```

