# Topic: Speculative Prefetch (VelesDB-inspired)

> status: exploring
> track: poc
> created: 2026-08-09
> baseline_trunk_sha: 3e98f3e
> baseline_status: current
> proposals: spec/open/proposal-poc-speculative-prefetch.md

## 探索表面

- `src/core/disk_hnsw.cpp` — searchLayer0() Phase 1-3 (block loading + candidate expansion)
- `src/core/disk_hnsw.cpp` — graph_prefetcher_ 1-hop prefetch (submitPrefetch)
- `src/core/disk_hnsw.cpp` — FineRerank (post-search, WILLNEED bg_thread)
- `src/core/block_cache.cpp` — getBlockById() cache miss → disk read
- `src/core/graph_prefetcher.cpp` — io_uring async prefetch

## 冲突/依赖检查

- bg-thread-futex (REJECTED): 不同瓶颈(CPU cache vs fadvise path), 无表面冲突
- sustained-param-retuning (PROMOTED): EF/ADAPTIVE 参数, 无代码冲突
- pipeline-param-retuning (PROMOTED): M_graph/PQ 参数, 无代码冲突

## 研究方向

| Round | 方向 | 瓶颈目标 | 方法 |
|-------|------|---------|------|
| R0 | Baseline profiling (金标环境) | 定位 | PROFILE_TS + perf stat under golden cgroup |

## 关联条款

- BEH-024 (WILLNEED), BEH-027 (WILLNEED_BG), DEC-070, DEC-074
- API-012 (L4 WILLNEED env), API-013 (WILLNEED_BG/VL_POOL env)
- CON-GOLDEN-001 (golden config), META-006 (golden update)
