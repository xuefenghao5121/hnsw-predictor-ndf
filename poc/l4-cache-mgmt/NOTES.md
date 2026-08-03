# L4 Page Cache 主动管理 - POC 笔记

> 提案: `spec/open/proposal-l4-cache-mgmt.md`（Pending r2）
> 条款: [[BEH-024]] draft
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

- [ ] 提案确认
- [ ] R0 基线复跑（验证 ~22.9 QPS 可复现）
- [ ] R1: 精准 DONTNEED（A）
- [ ] R2: +WILLNEED（A+B）
- [ ] R3: +选择性（A+B+D，`FINE_FADVISE` / `L4_SELECTIVE`）
- [ ] 数据分析 + 决策
