# Behavior — 搜索路径

> 条款索引: `BEH-001`, `BEH-002`, `BEH-003`, `BEH-004`, `BEH-005`, `BEH-006`, `BEH-008`

## 搜索流程状态机 {#BEH-001}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

DiskHNSW 搜索 MUST 遵循以下状态转移：

```
[查询到达] → Phase0: greedyDescent (L_high → L1)
           → PhaseA: searchLayer0 (PQ ADC, ef=REFINE_EF or ef_search)
           → PhaseB: FineRerank (4KB page reads, exact L2)
           → [返回 top-K]
```

**Phase B 精排子状态机** (from `disk_hnsw.cpp:1688-1913`):

```
[Phase A 候选] → 遍历候选
  ├─ cache hit (block cache or flat_vec_cache) → 立即算 L2 → consider()
  └─ cache miss
       ├─ FINE_PREAD=1 → pread 批量 4KB 读 → consider() + putFlatVector()
       └─ FINE_PREAD=0 → io_uring 批量提交 4KB 读
            ├─ FINE_MERGE=1 → 合并相邻页 8KB
            └─ FINE_MERGE=0 → 单页 4096B
            → waitCompletion + reap → consider() + putFlatVector()
```

## 搜索模式分支 {#BEH-002}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

`searchKnn()` 在 `disk_hnsw.cpp:1601` 中 MUST 根据环境变量选择搜索策略：

| 环境变量 | 模式 | 函数 |
|----------|------|------|
| `TWO_STAGE=1` + PQ | 两阶段搜索 | `searchLayer0()` (ef=REFINE_EF) → FineRerank |
| `BEAM_WIDTH>0` | Beam search | `searchLayer0Beam()` |
| `NONBLOCK=1` | 非阻塞 I/O overlap | `searchLayer0NonBlocking()` |
| `BATCH_IO_N>0` | 批量并行 I/O | `searchLayer0BatchIO()` |
| 默认 | 标准 best-first | `searchLayer0()` (ef=ef_search) |

## Layer 0 搜索核心循环 {#BEH-003}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-001 -->

所有 `searchLayer0*` 变体 MUST 使用相同的核心循环结构（`disk_hnsw.cpp:390-820`）：

```
while candidate_set not empty:
  pop candidate with min distance
  if candidateDist > lowerBound AND |top_candidates| == ef: break
  获取邻居列表 (CSR in-mem > CachedBlock)
  对每个未访问邻居：
    ├─ PQ mode → pqDistance() (ADC 查表)
    ├─ PQ_HYBRID=1 + cache hit → exact L2
    ├─ in-cache → exact L2
    └─ miss → pending list → batch wait I/O → exact L2
    如果距离 < lowerBound 或 |top_candidates| < ef:
      加入 candidate_set 和 top_candidates
      更新 lowerBound = top_candidates.top().first
```

## 贪心下降 {#BEH-004}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-001 -->

`greedyDescent()` (`disk_hnsw.cpp:343-384`) MUST:
1. 从 `entry_point` 开始，从 `max_level` 向下到 Layer 1
2. 每层：遍历当前节点在该层的邻居，如果找到更近的邻居就移动过去
3. 重复直到在当前层没有更近的邻居
4. 完全在内存中操作（上层向量 + 上层邻接表），零 I/O

## PQ 距离计算 {#BEH-005}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-001 -->

`pqDistance()` (`disk_hnsw.cpp:301-337`) MUST 分两条路径：

1. **查表快路径**（`pq_dist_table_` 非空时）：
   - 展开循环 4 路并行（m+0..m+3 同时查表累加）
   - 退化为 `M * ksub` 表查值 + 加法

2. **ADC fallback**（距离表未构建时）：
   - 直接计算 `|query_sub - centroid|²`
   - 每个子向量独立计算后累加

## PQ 距离表构建 {#BEH-006}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-005 -->

`buildPqDistTable()` (`disk_hnsw.cpp:244-299`) MUST 分支：
- **`dsub == 4`**: AVX2 路径，一次处理 2 个 centroid (8 floats)，用 `_mm256_sub_ps` + `_mm256_mul_ps` + `_mm_hadd_ps` 水平加法
- **`dsub != 4`**: 标量路径，三重循环 (M × ksub × dsub)
- 结果存入 **thread_local** `pq_dist_table_`，保证多线程安全

## 邻接表访问策略 {#BEH-008}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-001 -->

`getInMemNeighbors()` (`disk_hnsw.h:333`) MUST 分三条路径：

1. **CSR 内存邻接表**（`has_inmem_adjacency_ == true`）：
   - 非压缩：直接返回 `&adj_csr_neighbors_[adj_csr_offsets_[new_id]]`
   - 压缩：解码 `adj_csr_compact_` 从 `adj_csr_byte_offsets_[new_id]` 到 `csr_decode_buf_` (thread_local)
2. **BlockCache fallback**: `CachedBlock::getNeighbors()`

