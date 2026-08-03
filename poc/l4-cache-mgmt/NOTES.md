# L4 Page Cache 主动管理 - POC 笔记

> 提案: `spec/open/proposal-l4-cache-mgmt.md`（Pending r2）
> 条款: [[BEH-024]] draft
> 装订器: `ndf/TOPIC.md`（[[BEH-025]]）
> 基线: SIFT1M 严格隔离 Buffered 1T=22.9 QPS ([[DEC-066]])
> 状态: 待确认
> 口径: 以提案 / [[BEH-024]] 为准；禁止把 `EVICT_PAGE_CACHE` 当有效旋钮

## 问题分析

### 预算（与提案统一）

```text
page_cache_budget ≈ memory.max − Peak_RSS
1T: 512 − 235 = 277MB
4T: 512 − 416 = 96MB
```

### RSS 构成（1T, 严格隔离基线）

| 组成 | 大小 | 生命周期 |
|------|------|----------|
| upper-layer vectors | 30MB | 静态 |
| CSR compressed | 47MB | 静态 |
| BlockCache slots | 64MB | 静态 |
| PQ codes | 31MB | 静态 |
| route table | 8MB | 静态 |
| flat_vec cache | 4MB | 静态 |
| graph metadata | ~5MB | 静态 |
| VisitedList (1T) | ~40MB | 每查询 |
| 其他 | ~48MB | 每查询 |
| **Init RSS** | **147MB** | |
| **Peak RSS 1T** | **235MB** | |
| **可用 page cache (1T)** | **277MB** | 512 - 235 |

### Page cache 行为（当前问题）

- peak file = 400MB（总分，含 graph/PQ 等，不只 vecblocks）
- 相对 277MB 预算明显偏高 → `max` events = 1523
- pgmajfault = 5（1T）/ 27（4T）
- 根因：buffered I/O 读入 page cache，OS LRU 不知 HNSW 热/冷
- **成功标准**：以 vecblocks 驻留/回收 + `max` events 为主监控；不以「总 file≤277」为硬门闩

### 优化方向（对齐提案机制 A–D）

1. **精准 DONTNEED（A）**：fine rerank 后对非热 vecblocks 页 `posix_fadvise(DONTNEED)`（POC env，如 `L4_DONTNEED`）
2. **WILLNEED（B）**：对热块 `posix_fadvise(WILLNEED)`（如 `L4_WILLNEED`）
3. **选择性页面驱逐（D）**：基于真旋钮 **`FINE_FADVISE`** 或 POC `L4_SELECTIVE`；**禁止**依赖幽灵 `EVICT_PAGE_CACHE`
4. **L3/L4 分层（C）**：BlockCache miss 时 `mincore` 探 L4 再 `pread`（仍拷贝，非零拷贝）

优先级：A → D → B → C。本 POC 优先于 pipe_ring_ 重测。

## 进度

- [x] 提案确认
- [x] R0 基线复跑（FINE_BUFFERED=1, true buffered）
- [x] R1: FINE_FADVISE=1（evict all after read）
- [ ] R2: +WILLNEED（A+B）
- [ ] R3: +选择性（A+B+D，`FINE_FADVISE` / `L4_SELECTIVE`）
- [ ] 数据分析 + 决策

## R0/R1 结果 (2026-08-03, 严格隔离 CON-SLA-014, 512MB cgroup, 200q, 1T)

| 指标 | R0 (Buffered) | R1 (+FADVISE) | 旧基线 (误用 O_DIRECT) |
|------|---------------|--------------|----------------------|
| QPS | **23.0** | **23.1** | 22.9 |
| Recall | 98.35% | 98.35% | 98.35% |
| RSS | 235MB | 235MB | 235MB |
| memory.peak | 512MB | 512MB | 512MB |
| max events | 1522 | 1523 | 1523 |
| peak anon | 249MB | 245MB | 246MB |
| peak file | 432MB | 459MB | 400MB |
| workingset_refault_file | 0 | 0 | 0 |
| pgmajfault | 6 | 6 | 5 |

### 关键发现

1. **R0 vs 旧基线几乎相同** (23.0 vs 22.9)：FINE_BUFFERED=1 vs fallback O_DIRECT 性能几乎一致。说明 vecblocks I/O 模式不是瓶颈差异点。

2. **FINE_FADVISE 无收益** (23.1 vs 23.0)：FINE_FADVISE 在 fine rerank 后驱逐读过的页，但：
   - peak file 反而更高 (459 vs 432MB) -- FADVISE 只驱逐 vecblocks 页，graph/PQ 的 file 页不受影响
   - max events 不变 (1523 vs 1522) -- 内核回收压力未减轻
   - workingset_refault_file = 0 -- 没有热页被反复淘汰的迹象

3. **page cache 的 400-460MB 主要是 graph/PQ 等元数据文件，不是 vecblocks**：
   - vecblocks 通过 fine rerank 的 pread 路径读取，每次只读 4KB 页
   - graph 文件 587MB 通过 ifstream 加载，全量读入 page cache
   - PQ codes 31MB 也是 ifstream
   - 即使 FINE_FADVISE 驱逐了 vecblocks 页，graph/PQ 的页仍占满 page cache

4. **真正问题：graph 文件加载（587MB）填满 page cache 预算**：
   - Init 阶段读 587MB graph 文件 -> page cache 被填满
   - 搜索时 vecblocks 的 pread 又往 page cache 塞页 -> 超预算 -> 内核回收
   - 但 workingset_refault=0 说明回收的不是热页，性能影响不大
   - **瓶颈不在 page cache 回收，而在 I/O 延迟本身**

### 下一步方向调整

R0/R1 结果表明机制 A（精准 DONTNEED）在当前场景下无收益。需要重新分析：

1. **graph 文件的 page cache 管理**：graph 587MB 在 init 后不再需要（CSR 已构建），应驱逐其 page cache
2. **BlockCache 的 O_DIRECT**：BlockCache 已用 O_DIRECT (io_mode=direct)，不走 page cache
3. **真正的 I/O 瓶颈**：43ms/query 中，Phase A (PQ 计算) + Fine Rerank I/O 各占多少？
4. **flat_vec_cache 效果**：64MB BlockCache 中的 flat_vec_cache 是否已覆盖热向量？

可能需要先做 profile 分析再决定 R2/R3 方向。
