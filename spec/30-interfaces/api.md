# Interfaces — 端点、入参、出参

## CLI 入口 {#OBS-API-001}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

### benchmark_diskhnsw

```
Usage: ./build/benchmark_diskhnsw <graph> <bfs> <blocks> <route> <data> <query> <gt> <k> <ef> <num_queries>

Positional:
  graph       — graph_structure.bin 路径
  bfs         — bfs_order.bin 路径
  blocks      — blocks.bin 路径
  route       — route_table.bin 路径
  data        — base.fvecs 路径 (仅读维度)
  query       — query.fvecs 路径
  gt          — ground_truth.bin 路径
  k           — top-K (int)
  ef          — ef_search (int)
  num_queries — 查询数量 (int)

Environment variables (全部可选):
  CACHE_MB         — BlockCache 大小 (MB), **必填**
  TWO_STAGE        — 1=两阶段搜索
  PQ_CODES_PATH    — PQ codes 文件路径
  PQ_HYBRID        — 1=cache 命中用精确 L2
  REFINE_EF        — Phase A 粗筛 ef (默认 200)
  FINE_RERANK      — 1=4KB 页粒度精排
  FINE_BUFFERED    — 1=buffered I/O
  FINE_PREAD       — 1=pread 替代 io_uring (多线程必须)
  FINE_MERGE       — 1=合并相邻 4KB 页为 8KB 读
  VEC_BLOCKS_PATH  — Vec-Only 块文件路径 (FINE_RERANK 必须)
  FLAT_VEC_MB      — 热向量 LRU cache 大小 (默认 4MB)
  NUM_THREADS      — >0=并发搜索线程数
  BATCH_SIZE       — >0=批处理模式
  PROFILE_TS       — 1=输出两阶段计时
  PROFILE_FINE     — 1=输出 fine rerank 细粒度计时
  PREFETCH_SW      — 0=关闭软件预取
```

### benchmark_hnswlib_native

```
Usage: ./build/benchmark_hnswlib_native <index> <query> <gt> <k> <ef> <num_queries>
```

### test_disk_hnsw

```
Usage: ./build/test_disk_hnsw <index> <graph> <bfs> <blocks> <route> <data> <query>
       [k=10] [ef=50] [cache_slots=64]
       [--io-mode=cached|direct|simulated] [--latency=100]
       [--layout=bfs|random] [--policy=lru|lfu|lru-k]
```

## Data Pipeline CLI {#OBS-API-002}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

### build_index
```
Usage: ./build/build_index <base.fvecs> <output.bin> <M> <ef_construction>
```

### extract_graph
```
Usage: ./build/extract_graph <index.bin> <graph.bin> <dim>
```

### bfs_reorder
```
Usage: ./build/bfs_reorder <graph.bin> <bfs.bin>
```

### write_blocks
```
Usage: ./build/write_blocks <graph.bin> <bfs.bin> <blocks.bin> <block_size>
```

### write_blocks_veconly
```
Usage: ./build/write_blocks_veconly <graph.bin> <bfs.bin> <vecblocks.bin> <block_size>
```

### gen_route
```
Usage: ./build/gen_route <blocks.bin> <route.bin>
```

### write_pq_blocks
```
Usage: ./build/write_pq_blocks <graph.bin> <bfs.bin> <pq_blocks.bin> <block_size>
```

### verify
```
Usage: ./build/verify
```

### prune_graph
```
Usage: ./build/prune_graph <graph.bin> <output.bin> <strategy> <R_max>
  strategy: degree_cap | mrng
```

## Python Scripts {#OBS-API-003}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

### train_pq.py
```
Usage: python3 scripts/train_pq.py <base.fvecs> <output.bin> [M]
  M 缺省: dim=128→32, dim=96→8, 其它→整除 dim 的最大 (≤dim//4)
Output format: PQCO binary
```

### gen_gt.py
```
Usage: python3 scripts/gen_gt.py <base.fvecs> <query.fvecs> <gt_out.bin> [K]
  K 缺省: 10
Output format: header 8B (n_queries:u32 + K:u32) + n_queries * K * uint64 ids
```

### build_pipeline.sh
```
Usage: bash scripts/build_pipeline.sh <base.fvecs> <前缀> <M> [query.fvecs] [K]
```

### compare_benchmark.sh
```
Usage: bash scripts/compare_benchmark.sh
  MEM=512M THREADS=4 K=10 EF=50 NQ=200 RUNS=3 bash scripts/compare_benchmark.sh
```

## 二进制文件格式 {#OBS-API-004}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

### Graph Structure (MAGIC_GRAPH = 0x47524148)

```
Offset  Size   Field
0       4      magic (0x47524148 "HARG")
4       4      version (1 or 2 for compressed)
8       4      num_nodes
12      4      dim
16      4      maxM
20      4      maxM0
24      4      entry_point
28      4      max_level (int32)
32      4      data_size
36      4      reserved
40      4      padding
44      N*4    levels[N]
44+N*4  N*dim*4 vectors[N*dim]
...     N*8    labels[N]
...     var    L0 adjacency lists (cnt:u16 + cnt*u32 per node)
...     var    upper adjacency lists
```

### Blocks (MAGIC_BLOCKS = 0x424C4B48)

```
Offset   Size   Field
0        4      magic (0x424C4B48 "HKLB")
4        4      version
8        4      block_size (64KB or 256KB)
12       4      num_blocks
16..4095 pad    (BLOCKS_FILE_HEADER_SIZE = 4096)
4096     block_size  Block[0]
4096+BS  block_size  Block[1]
...

Per Block:
  0        4      block_id
  4        4      node_count
  8        4      data_offset
  12       4      adj_offset
  16       1      flags (bit0: delta_varint, bit1: vec_only)
  17       7      reserved_pad
  24       var    node_ids[count]
  data_off var    vectors[count*dim]
  adj_off  var    adjacency lists
```

### Route Table (MAGIC_ROUTE = 0x524F5554)

```
Offset   Size   Field
0        4      magic (0x524F5554 "ROUT")
4        4      num_entries (= num_nodes)
8        4      block_size
12       4      reserved
16       N*4    route[N] (node_id → block_id, uint32)
```

### BFS Order (MAGIC_BFS = 0x42465300)

```
Offset   Size   Field
0        4      magic (0x42465300 "BFS\0")
4        4      num_nodes
8        4      entry_point
12       4      reserved
16       N*4    old_to_new[N]
16+N*4   N*4    new_to_old[N]
```

### PQ Codes (magic "PQCO")

```
Offset   Size   Field
0        4      magic "PQCO"
4        8      n (uint64)
12       4      M (uint32)
16       4      nbits (uint32)
20       4      dim (uint32)
24       4      codebook_M (uint32)
28       4      codebook_K (uint32)
32       4      codebook_dsub (uint32)
36       M*K*dsub*4 codebook floats
...      n*M     pq_codes bytes (old_id order)
```

### Ground Truth (GT)

```
Offset   Size   Field
0        4      n_queries (uint32)
4        4      K (uint32)
8        n*K*8  neighbor_ids (uint64, only ids, no distances)
```

### FVECS

```
Per record: dim(int32) + dim * float32
```

## DiskHNSW Public API {#OBS-API-005}
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

## BlockCache Public API {#OBS-API-006}
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
