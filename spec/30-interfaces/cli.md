# Interfaces — CLI / Pipeline / Scripts

> 条款索引: `API-001`, `API-002`, `API-003`, `API-016`, `API-019`

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
  FLAT_VEC_MB      — 热向量 LRU cache 大小 (默认 64MB；见 [[API-011]] / [[CON-002]])
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
Usage: bash scripts/build_pipeline.sh <base.fvecs|base.hdf5> <前缀> <M> [query.fvecs|query.hdf5] [K]

支持 HDF5 自动转换 (ann-benchmarks 格式: /train, /test, /neighbors)
  .h5/.hdf5 输入自动调用 hdf5_to_fvecs.py 转换后继续 pipeline

# fvecs 输入
bash scripts/build_pipeline.sh data/sift_base.fvecs sift1m 32 data/query.fvecs 10

# HDF5 输入 (自动检测 /train /test /neighbors)
bash scripts/build_pipeline.sh data/sift-128-euclidean.hdf5 sift1m 32
```

### hdf5_to_fvecs.py
```
Usage: python3 scripts/hdf5_to_fvecs.py <hdf5_path> --prefix <前缀> [options]
  --out-dir DIR       输出目录 (默认当前目录)
  --base-key KEY      base dataset 名称 (默认自动检测: train/data/vectors)
  --query-key KEY     query dataset 名称 (默认自动检测: test/query/queries)
  --gt-key KEY        GT dataset 名称 (默认自动检测: neighbors/ground_truth)
  --k K               GT top-K (默认 10)
  --inspect           仅查看 HDF5 结构

输出:
  <prefix>_base.fvecs    base 向量
  <prefix>_query.fvecs   query 向量 (如有)
  <prefix>_gt10.bin      GT bin (如有 neighbors)
```

### compare_benchmark.sh
```
Usage: bash scripts/compare_benchmark.sh
  MEM=512M THREADS=4 K=10 EF=50 NQ=200 RUNS=3 bash scripts/compare_benchmark.sh
```


## cgroup 测试脚本接口 {#API-016}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.7 source=observed topic=cgroup-v1-support -->
<!-- ndf: depends-on=BEH-032,DEC-079,CON-SLA-014 -->

> **track: promoted** - 提案 `spec/open/proposal-cgroup-v1-support.md`（2026-08-06）。
> source: poc/cgroup-v1-support/ndf/TOPIC.md ; ../../spec/open/proposal-cgroup-v1-support.md

### cgroup_utils.sh

测试脚本 MUST 通过 `source scripts/cgroup_utils.sh` 引入兼容层，使用以下统一接口：

| 函数 | 参数 | 说明 |
|------|------|------|
| `cg_detect_version` | 无 | 返回 `v2` / `v1` / `unknown` |
| `cg_init` | name, limit_mb | 初始化 cgroup 环境（设置 CG_VERSION/CG_PATH 等） |
| `cg_create` | 无 | 创建 cgroup（v1: memory controller 子目录） |
| `cg_set_limit` | limit_mb | 设置内存限制（v2: `memory.max`; v1: `memory.limit_in_bytes`） |
| `cg_get_memory` | 无 | 输出 3 行：anon_bytes / file_bytes / total_bytes |
| `cg_get_peak` | 无 | 返回内存峰值（bytes） |
| `cg_check_violations` | 无 | 返回违规计数（v2: oom+oom_kill; v1: failcnt） |
| `cg_stats_summary` | 无 | 输出完整统计摘要（统一格式） |
| `cg_start_monitor` | logfile | 启动后台内存监控（100ms 采样，PID 写入 CG_MONITOR_PID） |
| `cg_stop_monitor` | pid | 停止后台监控 |
| `cg_verify` | 无 | 严格验证：peak ≤ limit AND violations = 0 |
| `cg_add_proc` | pid | 将进程加入 cgroup |
| `cg_destroy` | 无 | 删除 cgroup |
| `cg_drop_caches` | 无 | sync + echo 3 > drop_caches |

环境变量 `CGROUP_FORCE_V1=1` 可强制使用 v1 路径（仅用于逻辑测试）。

## 多轮采样 benchmark CLI {#API-019}
<!-- ndf: kind=interface level=must layer=L1 status=stable since=0.9.10 source=observed topic=sustained-query-benchmark trunk-ref=47ed9e7 -->
<!-- ndf: refines=API-002 -->

> **track: promoted** - 提案 `spec/open/proposal-promote-sustained-query-benchmark.md`（2026-08-06）。
> 装订器: `poc/sustained-query-benchmark/ndf/TOPIC.md`。

`benchmark_sustained` 命令行接口，实现 [[BEH-035]]。

### 位置参数

```
Usage: ./build/benchmark_sustained <graph> <bfs> <blocks> <route> <data> \
                                   <query_pool> <gt> <k> <ef> [options]
```

与 `benchmark_diskhnsw`（[[API-002]]）保持一致，除 `<query>` 改为 `<query_pool>`
且 `<num_queries>` 由 `--per-round` 选项替代。

### 选项

| 选项 | 默认 | 说明 |
|------|------|------|
| `--rounds R` | 10 | 统计轮数 |
| `--per-round N` | 200 | 每轮采样 query 数 |
| `--seed S` | 42 | 随机种子基值（第 `i` 轮用 `S+i`） |
| `--warmup W` | 0 | warmup 轮数，不计入统计（seed 空间 `S+1000000+w`，与统计轮 disjoint） |
| `--verbose` | off | 输出每轮明细 |

### 环境变量

MUST 要求 `CACHE_MB`（缺失时 MUST 报 `ERROR: CACHE_MB required` 并非零退出）。
其余旋钮沿用 `benchmark_diskhnsw` 约定（见 [[API-002]] 与 `spec/30-interfaces/env.md`）。

### 测试脚本绑定

`scripts/run_sustained.sh` 是 [[CON-SLA-020]] sustained 测试的**权威载体**（[[CON-SLA-014]]
严格 cgroup 隔离 via [[API-016]] `scripts/cgroup_utils.sh`）。

支持 `--config <config_id>` 从 `spec/50-verification/configs/<config_id>.md`
读取金标配置参数（`data_path`, `REFINE_EF`, `ADAPTIVE_*` 等）。Env 显式设置优先于
`--config` 解析值。`--dry-run` 打印参数不执行。

`scripts/run_golden.sh` 是 [[CON-GOLDEN-001]] 金标自动化的**权威载体**，
覆盖全部三组金标配置（A/B/C）× 4 场景 × 3 轮。

### GT 格式

`<gt>` 接受两种格式，MUST 按扩展名判定：

| 扩展名 | 格式 |
|--------|------|
| `.ivecs` | 官方格式：每条 `int32 dim` + `dim × int32` |
| `.bin` | 内部格式：`uint32 n` + `uint32 k` + `n×k × uint64` |

### 输出

人读段落之后 MUST 输出机读 CSV 尾部，便于扫描脚本解析：

```
CSV_HEADER,round,queries,elapsed_s,qps,recall,cumulative_unique
CSV_ROW,1,200,0.817,244.7,0.9535,200
...
CSV_AGG,<rounds>,<total_queries>,<total_s>,<qps>,<recall>,<unique>,<last_round_qps>
```

> rationale: 复用现有 benchmark 位置参数约定降低学习成本；GT 双格式支持使官方
> `.ivecs` 可直接使用，无需转换；CSV 尾部使 sweep 脚本无需正则解析人读文本。
> source: poc/sustained-query-benchmark/ndf/proposals/draft-clauses.md @ 4a33f38
