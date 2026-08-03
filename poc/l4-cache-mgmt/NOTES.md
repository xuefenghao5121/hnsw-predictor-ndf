# L4 Page Cache 主动管理 - POC 笔记

> 提案: `spec/open/proposal-l4-cache-mgmt.md`（Implemented）
> 条款: [[BEH-024]] draft
> 基线: SIFT1M 严格隔离 Buffered 1T ([[DEC-066]])
> 状态: R0-R3 v2 完成（修正 PQ_CODES_PATH），FINE_FADVISE 有害，EvictMeta 微正
> 口径: 以提案 / [[BEH-024]] 为准；禁止把 `EVICT_PAGE_CACHE` 当有效旋钮

## ⚠️ 重大发现：环境变量名错误 (2026-08-03)

**R0-R3 v1 全部作废。** benchmark 读 `PQ_CODES_PATH`（带 S），但 v1 脚本设的是 `PQ_CODE_PATH`（不带 S）。

PQ codes 未加载 -> `pq_enabled_=false` -> 走普通 searchLayer0NonBlocking（无 PQ 粗筛、无 fine rerank）-> Recall=98.35%（全量精排）但 QPS=23（极慢）。

修正后 QPS 从 23 跳到 2309（100x）。

## 预算

```text
page_cache_budget ≈ memory.max − Peak_RSS
1T: 512 − 155 = 357MB（修正后 RSS 降至 155MB，因 PQ 替换 upper vectors 释放 30MB）
```

## R0-R3 v2 结果 (2026-08-03, 严格隔离 CON-SLA-014, 512MB cgroup, 200q, 1T)

| 指标 | R0 (Buffered) | R1 (+FADVISE) | R2 (+EvictMeta) | R3 (+Both) |
|------|---------------|--------------|-----------------|------------|
| QPS | **2309** | **133** | **2383** | **132** |
| Recall | 95.75% | 95.75% | 95.75% | 95.75% |
| Mean | 0.43ms | 7.49ms | 0.42ms | 7.60ms |
| RSS | 155MB | 155MB | 155MB | 155MB |
| memory.peak | 512MB | 512MB | 512MB | 512MB |
| max events | 1654 | 1523 | 1526 | 1526 |
| peak file | 420MB | 428MB | 393MB | 407MB |
| file (end) | 374MB | 370MB | 181MB | 143MB |
| workingset_refault_file | 0 | 0 | 0 | 0 |
| pgmajfault | 6 | 6 | 6 | 6 |

### 机制说明

| 轮次 | 机制 | 说明 |
|------|------|------|
| R0 | FINE_BUFFERED=1 | True buffered I/O for vecblocks (基线) |
| R1 | + FINE_FADVISE=1 | Fine rerank 后驱逐 vecblocks 页 (机制 A) |
| R2 | + L4_EVICT_META=1 | Init 后驱逐 graph+BFS 页 (新机制) |
| R3 | + 两者 | 同时驱逐 vecblocks + graph+BFS |

### Profile 分解（PROFILE_TS=1, 200q × 2 批）

```
R0: n=200 PhaseA=-2953us pread=9448us rerank=45us -> n=400 PhaseA=-1486us pread=4782us rerank=27us
R1: n=200 PhaseA=-2903us pread=10001us rerank=43us -> n=400 PhaseA=-1474us pread=8313us rerank=38us
R2: n=200 PhaseA=-2904us pread=9383us rerank=43us -> n=400 PhaseA=-1461us pread=4748us rerank=26us
R3: n=200 PhaseA=-2706us pread=9725us rerank=38us -> n=400 PhaseA=-1375us pread=8227us rerank=35us
```

- Phase A：负值（计时插桩 bug，tpA < tp0，待修）
- **pread (Fine I/O)：R0/R2 从 9.4ms 降到 4.8ms（page cache 预热 2x）；R1/R3 从 10ms 只降到 8.3ms（FADVISE 阻止预热）**
- rerank (L2 计算)：27-45μs（极快，不是瓶颈）
- **Fine I/O 占总延迟 95%+**

### 关键发现

1. **FINE_FADVISE 导致 17x 性能下降**（2309 -> 133 QPS）
   - 每次 fine rerank 后驱逐 vecblocks 页 -> 下次查询必须重新从磁盘读
   - page cache 无法跨 query 积累，每次都是冷读
   - pread 从 4.8ms 涨到 8.3ms（热态），证明 page cache 命中被破坏

2. **R2 (EvictMeta) 反而最快**（2383 QPS，比 R0 快 3%）
   - 驱逐 graph+BFS 的 page cache 释放了预算给 vecblocks
   - file (end) 从 374MB 降到 181MB -- graph 页被驱逐，vecblocks 页保留
   - vecblocks 获得更多 page cache 空间，QPS 微升

3. **page cache 对 vecblocks 极其关键**：
   - R0/R2（无 FADVISE）：前 200q pread=9.4ms，后 200q pread=4.8ms（page cache 预热，2x 加速）
   - R1/R3（有 FADVISE）：前 200q pread=10ms，后 200q pread=8.3ms（page cache 被驱逐，无法预热）

4. **workingset_refault_file = 0（所有轮次）**：内核 LRU 没有误杀热页，无需 WILLNEED

### 核心结论

- **FINE_FADVISE 在严格隔离下是有害的**：驱逐 vecblocks 页破坏跨 query page cache 预热
- **L4_EVICT_META 有微小正收益**：驱逐 graph 页释放预算给 vecblocks，QPS +3%
- **真实瓶颈是 Fine I/O (pread)**：占总延迟 95%+，page cache 命中率是关键杠杆
- **后续方向**：如何在预算内最大化 vecblocks page cache 命中率（而非驱逐它）

## 进度

- [x] 提案确认
- [x] R0-R3 v1（作废：PQ_CODES_PATH 拼写错误）
- [x] R0-R3 v2（修正后）
- [x] Profile 分析：Fine I/O 是瓶颈，page cache 命中是关键
- [ ] 决策：L4_EVICT_META 是否值得 promote / FINE_FADVISE 是否需要标注有害
