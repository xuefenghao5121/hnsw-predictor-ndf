# Topic: Speculative Prefetch (VelesDB-inspired)

> status: rejected
> track: poc
> created: 2026-08-09
> baseline_trunk_sha: 3e98f3e
> baseline_status: current
> close_reason: R0 negative result — FineRerank 0.06% of query time, no ceiling for prefetch
> proposals: spec/open/proposal-poc-speculative-prefetch.md

## 探索表面

- `src/core/disk_hnsw.cpp` — search loop, FineRerank PQ ADC
- `src/core/disk_hnsw.cpp` — bg_thread WILLNEED path (BEH-024/BEH-027)
- FineRerank batch distance computation (CPU cache behavior)
- Layer switching I/O wait window

## 冲突/依赖检查

- bg-thread-futex (REJECTED): 不同瓶颈(CPU cache vs fadvise path), 无表面冲突
- sustained-param-retuning (PROMOTED): EF/ADAPTIVE 参数, 无代码冲突
- pipeline-param-retuning (PROMOTED): M_graph/PQ 参数, 无代码冲突

## 研究方向

| Round | 方向 | 瓶颈目标 | 方法 |
|-------|------|---------|------|
| R0 | Baseline profiling | 定位 | perf cache-miss + strace pread latency |
| R1 | CPU prefetch PQ ADC | CPU L1/L2 miss | `_mm_prefetch` in PQ ADC loop |
| R2 | Speculative WILLNEED | Disk I/O wait | next-layer candidate prediction |
| R3 | Batch prefetch pipeline | Memory latency | candidate list batching |

## 关联条款

- BEH-024 (WILLNEED), BEH-027 (WILLNEED_BG), DEC-070, DEC-074
- API-012 (L4 WILLNEED env), API-013 (WILLNEED_BG/VL_POOL env)
- CON-GOLDEN-001 (golden config), META-006 (golden update)
