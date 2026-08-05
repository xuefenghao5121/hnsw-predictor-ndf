# Interfaces — C++ Public API

> 条款索引: `API-005`, `API-006`

## DiskHNSW Public API {#API-005}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

```cpp
class DiskHNSW {
  // 构造函数
  DiskHNSW(graph_path, bfs_path, blocks_path, route_path, cache_slots=64, dim=128);
  DiskHNSW(graph_path, bfs_path, unique_ptr<BlockCache>);

  // 搜索
  vector<SearchResult> searchKnn(query, k);                    // 单查询
  vector<vector<SearchResult>> batchSearch(queries, k, batch); // 事件驱动批量
  vector<vector<SearchResult>> batchSearchConcurrent(queries, k, threads); // 多线程

  // 配置
  void setEf(ef);
  void loadPQCodes(pq_path);
  void enableGraphPrefetch(use_odirect=true);

  // 查询
  bool isPQEnabled();
  bool isGraphPrefetchEnabled();
  uint32_t getNumNodes();
  uint32_t getDim();
};
```

## BlockCache Public API {#API-006}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

```cpp
class BlockCache {
  BlockCache(blocks_path, unique_ptr<LayoutProvider>, unique_ptr<ReplacementPolicy>,
             cache_slots, dim, IOConfig);
  BlockCache(blocks_path, route_path, cache_slots, dim, IOConfig);

  // 节点级
  const float* getNodeVector(node_id);
  const uint32_t* getNodeNeighbors(node_id, out_count);

  // Block 级
  CachedBlock* getBlockByNodeId(node_id);
  CachedBlock* getBlockById(block_id);
  CachedBlock* getCachedBlockById(block_id);  // miss 不触发加载
  CachedBlock* peekCachedBlockById(block_id); // 不加锁不触发加载

  // 预取
  bool isInCache(block_id);
  vector<uint32_t> filterNotInCache(block_ids);
  bool insertBlock(block_id, raw_data, size);
  bool insertBlockFromPtr(block_id, data, size);
  bool insertBlocksBatch(entries);

  // Flat Cache (lock-free)
  const float* getFlatVector(node_id);
  void putFlatVector(node_id, vec);
  void prefetchFlatSlot(node_id);

  // 路由
  uint32_t getBlockId(node_id);
  uint32_t getNumNodes();
  uint32_t getNumBlocks();

  // 统计
  const Stats& getStats();
  const FlatStats& getFlatStats();
  double hitRate();
};
```

