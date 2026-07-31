# Interfaces — CLI / Pipeline / Scripts

> 条款索引: `API-001`, `API-002`, `API-003`

## CLI 入口 {#API-001}
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
      PAGE_SEARCH      — 1=Fine Rerank 页内全向量扫描 (DEC-017)
      DYNAMIC_WIDTH    — 1=Phase A 自适应 efSearch 宽度 (DEC-019)
      DW_CONVERGE_HOP  — Dynamic Width 收敛跳数 (默认 10)
      DW_DECAY         — Dynamic Width 衰减率 (默认 0.75)
      EF_SEARCH_MIN    — Dynamic Width 最小 efSearch (默认 32)
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

## Data Pipeline CLI {#API-002}
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

## Python Scripts {#API-003}
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

