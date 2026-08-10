# Proposal: mmap Read-Only Data to Shift Anon→File Budget

> status: rejected
> track: poc
> created: 2026-08-09
> baseline_trunk_sha: 434c6f5
> baseline_status: current

## 背景

### R0 发现链

1. **speculative-prefetch R0**: LLC miss 58.1% 是真正瓶颈（不是 disk I/O 也不是 L1 miss）
2. **data-layout R0**: 布局优化天花板仅 ~4%（PQ code 32B 限制 cache line sharing）
3. **用户洞察**: 回忆 L4 cache 设计——cgroup budget = anon + file，可以 trade anon for page cache

### Cgroup 内存预算（DEC-088 实测，256MB cgroup, SIFT1M M=16, 1T）

```
cgroup_limit (256MB) = anon (~229MB) + file (~27MB page cache)

anon breakdown:
  Graph upper vectors:  30MB    ← read-only, 可 mmap
  CSR adjacency:        47MB    ← read-only, 可 mmap (需序列化)
  PQ codes:             30MB    ← read-only, 可 mmap (需 BFS 重排后序列化)
  flat_vec_cache:       64MB    ← read-write (LRU 管理), 不能 mmap
  Block cache:          64MB    ← read-write (LRU 管理), 已有 mmap 选项
  VisitedList+misc:      5MB    ← read-write, 不能 mmap
```

### 核心洞察

**read-only 数据结构（PQ codes + CSR + graph upper）共 107MB 目前占用 anon 预算。**

如果将这些数据改为 mmap（file-backed），anon 预算从 229MB 降至 122MB，
file（page cache）预算从 27MB 增至 134MB。

**5x 更多 page cache → vecblocks 覆盖率从 5.4% 提升到 27%！**

### 与之前两个 POC 的关系

| POC | 结论 | 本提案的关系 |
|-----|------|-------------|
| speculative-prefetch | REJECTED: disk I/O 仅 3% | 本提案不针对 disk I/O，而是 anon/file 预算重新分配 |
| data-layout-optimization | REJECTED: LLC miss 布局优化天花板 ~4% | 本提案不优化布局，而是改变数据在 cgroup 中的记账方式 |

本提案开辟了一个全新的优化维度：**不是减少 cache miss，而是增大 cache 预算**。

## 设计

### 方案：mmap read-only 数据结构

| 数据结构 | 当前 | 改进 | 大小 | 节省 anon |
|----------|------|------|------|-----------|
| PQ codes | `std::vector<uint8_t>` (anon) | `mmap(MAP_PRIVATE)` from pre-built BFS-order file | 30MB | 30MB |
| CSR adjacency | in-memory `std::vector` (anon) | `mmap(MAP_PRIVATE)` from serialized CSR file | 47MB | 47MB |
| Graph upper vectors | `std::vector<float>` (anon) | `mmap(MAP_PRIVATE)` from graph.bin (already file-backed!) | 30MB | 30MB |

**总计释放 107MB anon 预算 → 107MB 更多 page cache。**

### 前置工作

1. **PQ codes BFS-order 文件**: 当前 PQ codes 在加载时按 BFS 重排（line 218-228）。
   需要先离线构建 BFS-order PQ codes 文件，然后直接 mmap。
   PQ 文件：`output/pqco_sift1m_M32_correct.bin`（M_pq=32, n=1M, 32MB codes）。
2. **CSR 序列化文件**: 当前 CSR 在 `buildInMemoryAdjacency()` 中从 graph.bin 构建，
   存储为 Delta+Varint 压缩格式（`adj_csr_compact_` + `adj_csr_byte_offsets_`，DEC-064）。
   需要离线序列化压缩 CSR 到文件，然后 mmap。
   R0 前需运行一次 M=24 配置，从日志获取 CSR 压缩后实际大小。
3. ~~**Graph upper vectors**~~: ~~已有文件（graph.bin 包含 vectors）。
   可以直接 mmap graph.bin 的 vector data 区域。~~
   **排除**：kUpperPQ=1（默认）下 upper vectors 已释放（DEC-034），稳态 0MB。

### cgroup v2 记账

- `mmap(MAP_PRIVATE, PROT_READ)` 的页面计入 cgroup 的 `file` 计数
- 第一次访问触发 page fault → 从磁盘读取 → 进入 page cache
- 后续访问命中 page cache（无 disk I/O）
- 页面可被 kernel LRU 回收（在内存压力下自动驱逐）
- `madvise(MADV_RANDOM)` 告诉内核这是随机访问模式

### 预期效果

| 指标 | 当前 (anon PQ+CSR+graph) | mmap 后 | 变化 |
|------|--------------------------|---------|------|
| anon RSS | 229MB | ~122MB | -107MB |
| file (page cache) | 27MB | ~134MB | +107MB |
| vecblocks coverage | 5.4% | 27% | **5x** |
| Major faults/query | 0.50 | ≤0.50 | 不恶化 |
| LLC miss rate | 58.1% | 可能降低 | page cache hit → 减少 I/O 路径 |

### 风险分析

| 风险 | 分析 | 缓解 |
|------|------|------|
| mmap page fault 开销 | 首次访问有 minor fault，但后续命中 page cache | madvise(MADV_WILLNEED) 预热 |
| PQ codes 访问延迟 | mmap 随机访问 vs vector 随机访问，本质相同 | 无差异（都是 DRAM 访问） |
| page cache 争夺 | mmap 的 PQ codes 页面与 vecblocks 页面竞争 page cache | kernel LRU 自动管理热/冷 |
| recall 变化 | 零风险（数据不变，仅加载方式改变） | 代码层面保证 |
| cgroup reclaim 抖动 | kernel 在内存压力下频繁 reclaim file pages | 需验证 sustained 性能稳定性 |

## R0 Plan

### 实验

1. **构建 BFS-order PQ codes 文件**（离线工具，M=24 数据集）
2. **在 benchmark 中用 mmap 加载 PQ codes**（修改 ~20 行）
3. **sustained 金标 A/B 对比**（256MB 1T, Config C: M=24 EF=60, 15轮×1000q）
   - A: 当前（vector 加载）
   - B: mmap 加载
4. **指标**: 聚合 QPS, 稳态 QPS, recall, anon/file 内存拆分, major faults, LLC miss rate

### R0 结果 (2026-08-10, scripts/run_sustained.sh 金标)

| | A (vector PQ) | B (mmap PQ) | Delta |
|--|:---:|:---:|:---:|
| agg QPS | 1,431.6 | 277.0 | **-80.6%** |
| steady QPS | 1,662.7 | 267.4 | **-83.9%** |
| recall | 96.60% | 96.60% | 0 ✅ |
| Ramp-up | 167.5% | 5.0% | mmap 无法热身 |

A vs 金标 1,450: −1.3%（±2CV 内 ✅）

**R0 PQ codes REJECTED**: PQ codes 30MB file-backed → page cache thrashing with vecblocks。
Ramp-up 仅 5%，mmap page fault 贯穿全部 15 轮。

### R1 假设

R0 证伪了 PQ codes mmap，但 CSR 与 PQ codes 的访问模式不同：

| | PQ codes | CSR |
|--|----------|-----|
| 大小 | 30MB | 57MB (Delta+Varint 压缩) |
| 访问频率 | 每 candidate 节点一次 | 每节点展开一次 |
| 单次访问 | 32B (固定) | 可变 (~2B/edge varint) |
| 空间局部性 | 无 (纯随机) | 有 (BFS 重排后相邻节点) |
| 工作集 | hot, 小量 | warm, 中量 |

CSR 的 BFS 重排后空间局部性更好（相邻 new_id 的 byte_offsets 连续），
可能减少 page cache 争夺。但 CSR 57MB > PQ 30MB，争夺面更大。
R1 用金标 A/B 验证。

### 关于与 R0 speculative-prefetch 的矛盾

speculative-prefetch R0 发现 major fault 仅 0.50/query（disk I/O 仅 3%）。
那么增加 page cache 有什么用？

**答案**: 
- 当前 0.50 major fault 是在 WILLNEED 完美覆盖下的结果
- 但 WILLNEED bg_thread 有 CPU 开销（sched_yield 自旋占 18.4% CPU）
- 更多 page cache → 更高的 cache 命中率 → 减少 WILLNEED 的工作量
- 同时，mmap 释放的 anon 预算也可以给 block_cache / flat_vec_cache 更多空间

## 协议

### 测试脚本

使用正式金标脚本 `scripts/run_sustained.sh`（API-019 / BEH-035 / VER-043），
该脚本通过 `source scripts/cgroup_utils.sh` 引入完整 CON-SLA-014 严格隔离协议：

- `cgroup_utils.sh`（API-016）是 cgroup 操作工具库，提供原语：
  cg_init / cg_create / cg_set_limit / cg_drop_caches / cg_add_proc /
  cg_stats_summary / cg_check_violations / cg_get_peak / cg_start_monitor /
  cg_stop_monitor / cg_verify / cg_destroy
- `run_sustained.sh` 是正式 sustained 测试脚本（CON-SLA-020 载体），调用上述原语

R0 的 A/B 对比使用 `run_sustained.sh`，A/B 唯一差异为 `PQ_MMAP_PATH` 环境变量。
M=24 Config C 参数通过 `EXTRA` 环境变量传入（REFINE_EF=60 ADAPTIVE_EF=0）。

> 注：`run_sustained.sh` 默认使用 M=16 数据路径和 EF=100。
> R0 需通过 EXTRA 覆盖数据路径和 EF 参数以适配 Config C。
> 如 `run_sustained.sh` 不支持自定义 binary 路径，需扩展脚本或创建
> `scripts/` 下的封装脚本（不是 poc/ 下）。

### 测试标准

- **CON-SLA-020** sustained query measurement（金标测试）
- **CON-SLA-019** 禁预热：MUST NOT 在计时窗口前或内部预热 query
- **CON-SLA-014** 严格 cgroup 隔离（cgroup_utils.sh 全流程）
- 15 轮 × 1000 query, seed=42, 官方 10K pool 随机采样
- 同时报告 **聚合 QPS**（含冷启动，SLA 判定口径）和 **稳态 QPS**（末轮，参考上限）
- cgroup 完整统计：anon/file/peak/violations/refault/majfault

### 基线配置

- **金标 Config C (DEC-087 Pareto 最优)**
  - M_graph=24, REFINE_EF=60, ADAPTIVE_EF=0, FLAT_VEC_MB=64
  - 数据路径: output/sift1m_m24/
  - 金标基线 (Trunk 434c6f5, 256MB 1T): agg 1,450 / steady 1,702 / recall 96.60%

### A/B 对比

- A (vector PQ): `build/benchmark_sustained`, 无 `PQ_MMAP_PATH`
- B (mmap PQ): `poc/mmap-budget-shift/build/benchmark_mmap`, `PQ_MMAP_PATH=output/sift1m_m24/sift1m_m24_pq_bfs.bin`
- 指标: 聚合 QPS, 稳态 QPS, recall, anon/file/peak/violations
- 约束: recall ≥ 95%, 不修改 Trunk src/

## 关联条款

- [[BEH-024]] (L4 Page Cache 主动管理)
- [[BEH-027]] (WILLNEED 后台线程化)
- [[DEC-034]] (Upper vectors PQ 释放, kUpperPQ 默认开启)
- [[DEC-064]] (CSR 逐节点释放 + Delta+Varint 压缩)
- [[DEC-068]] (flat_vec_cache + O_DIRECT fix)
- [[DEC-070]] (WILLNEED readahead promote)
- [[DEC-088]] (内存预算驱动因果模型)
- [[CON-SLA-014]] (cgroup 隔离)
- [[CON-SLA-019]] (禁预热)
- [[CON-SLA-020]] (sustained query measurement)
- [[CON-GOLDEN-001]] (金标配置)
