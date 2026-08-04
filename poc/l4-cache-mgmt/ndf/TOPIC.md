# TOPIC: l4-cache-mgmt

> topic_id: l4-cache-mgmt
> status: exploring (R5 amendment; R4 promoted subset in Trunk as BEH-024 stable)
> baseline_protocol: [[CON-SLA-014]] + SIFT1M；基线见 [[DEC-067]]（修正后）
> depends_on_topics: (none; **this topic precedes** io-pipelining re-bench)
> binder: [[DEF-022]] / [[BEH-025]]

## Active hypothesis

严格隔离下 page cache 预算不足时内核盲目 LRU 误杀热页；
对 vecblocks 做精准 DONTNEED / WILLNEED / 选择性驱逐，可减少 workingset_refault，抬升 QPS。

## 实验进展

### Phase 1: R0-R3 v2 (512MB cgroup, PQ_CODES_PATH 修正后)

**结论：512MB 下 page cache 充裕，L4 管理无显著收益。**

| 轮次 | 机制 | QPS | refault | 结论 |
|------|------|-----|---------|------|
| R0 | Buffered 基线 | 2309 | 0 | 基线 |
| R1 | +FINE_FADVISE (evict vecblocks) | 133 | 0 | ❌ 17x 下降 |
| R2 | +L4_EVICT_META (evict graph) | 2383 | 0 | ✅ +3% |
| R3 | +两者 | 132 | 0 | ❌ FADVISE 主导 |

### Phase 2: 紧 cgroup 实验 (256/192/160MB)

**结论：256MB 是分水岭，page cache 不足导致 refault 暴涨。L4 管理的有效场景。**

| cgroup | page cache 预算 | QPS | refault | majfault | 场景 |
|--------|----------------|-----|---------|----------|------|
| 512MB | 357MB | 2309 | 0 | 6 | 充裕 |
| 256MB | 103MB | 126 | 30326 | 5078 | **不足，L4 有效** |
| 192MB | 62MB | 134 | 31212 | 13535 | 不足 |
| 160MB | 40MB | 124 | 35376 | 30544 | 不足 |

### O_DIRECT 4T bug 修复

根因：`if (kFinePread && !kFineDirect)` 跳过 pread 走了非线程安全 io_uring。
修复：改为 `if (kFinePread)` + `posix_memalign`。Recall 12.40% -> 95.75%。

## Next gate

- [x] R4: flat_vec_cache 在 fine rerank 中命中 + 增大扫描 -> **promoted** (BEH-024 stable, DEC-068)
- [x] R5a: WILLNEED 测试 -> **18.5x QPS! 候选 promote**
- [x] R5b: Selective DONTNEED 测试 -> refault 消除, QPS +14%
- [x] R5d: 组合测试 -> WILLNEED alone 最优
- [x] 512MB 回归验证 -> **无回归** ✅ (+3.7%)
- [x] 决策：WILLNEED promote 到 Trunk -> **promoted** (DEC-070, BEH-024 amend, API-012)
- [x] DEEP10M WILLNEED 验证 -> 中性（I/O 量是瓶颈，不是时序）
- [ ] R5c: mincore 诊断 (低优先级)

## R4 结果 (2026-08-03)

**发现**：fine rerank 未查 flat_vec_cache，热向量走 pread。加入 check + 增大 cache：

| flat_vec | cgroup | QPS | refault | 提升 |
|----------|--------|-----|---------|------|
| 4MB | 256MB | 126 | 30326 | 基线 |
| 64MB | 256MB | **947** | 4048 | **7.5x** |

核心洞察：把热向量从 page cache (OS) 移到 flat_vec_cache (进程内) 更有效。

## Draft clauses

| ID | In spec/? | Notes |
|----|-----------|-------|
| [[BEH-024]] | yes (`status=draft`) | L4 主动管理；禁 EVICT 幽灵 |

## Proposals

| Role | Path | Status |
|------|------|--------|
| root | `spec/archive/2026-08/proposal-l4-cache-mgmt.md` | Implemented (archived) |
| root | `spec/open/proposal-promote-l4.md` | Implemented |
| amend | `poc/l4-cache-mgmt/ndf/proposals/proposal-l4-r5-willneed-selective.md` | Pending |

## Evidence

| date | round | cgroup | QPS | refault | majfault | pread(热) | note |
|------|-------|--------|-----|---------|----------|-----------|------|
| 2026-08-03 | R0 v2 | 512MB | 2309 | 0 | 6 | 4.8ms | 基线，page cache 充裕 |
| 2026-08-03 | R1 v2 | 512MB | 133 | 0 | 6 | 8.3ms | +FINE_FADVISE, ❌ 17x 下降 |
| 2026-08-03 | R2 v2 | 512MB | 2383 | 0 | 6 | 4.7ms | +EvictMeta, ✅ +3% |
| 2026-08-03 | R3 v2 | 512MB | 132 | 0 | 6 | 8.2ms | +both, FADVISE 主导 |
| 2026-08-03 | tight-256 | 256MB | 126 | 30326 | 5078 | 8.4ms | page cache 不足，refault 暴涨 |
| 2026-08-03 | tight-192 | 192MB | 134 | 31212 | 13535 | 8.4ms | 同上 |
| 2026-08-03 | tight-160 | 160MB | 124 | 35376 | 30544 | 8.7ms | 同上 |

### 作废数据

| date | round | QPS | note |
|------|-------|-----|------|
| 2026-08-03 | R0-R3 v1 | 23 | **作废**: PQ_CODES_PATH 拼写错误 |

## Commits

见 [COMMITS.md](COMMITS.md)

## R5 Evidence (2026-08-04)

| date | round | cgroup | mechanism | QPS | refault | majfault | RSS | vs base | note |
|------|-------|--------|----------|-----|---------|----------|-----|---------|------|
| 2026-08-04 | R5-base | 256MB | none (promoted) | 136 | 27439 | 5103 | 153MB | 1x | baseline |
| 2026-08-04 | R5a | 256MB | +WILLNEED | **2521** | **0** | 5039 | 153MB | **18.5x** | kernel readahead pipelining |
| 2026-08-04 | R5b | 256MB | +SelDONTNEED | 155 | **2** | 5025 | 153MB | +14% | refault eliminated, QPS modest |
| 2026-08-04 | R5d | 256MB | +Both | 965 | 0 | 4978 | 153MB | 7.1x | SelDONTNEED hurts WILLNEED |
| 2026-08-04 | R1-ref | 256MB | blanket FADVISE | 144 | 0 | 5074 | 153MB | +6% | no harm at 256MB (vs 512MB -17x) |

### R5 Key Findings

1. **WILLNEED = free I/O pipelining**: `posix_fadvise(WILLNEED)` before pread loop causes kernel readahead to run asynchronously. By the time pread runs, pages are already in page cache. 18.5x QPS improvement.
2. **Selective DONTNEED eliminates refault**: refault 27439->2, but QPS only +14% (majfault unchanged = disk I/O is real bottleneck).
3. **Combining hurts**: WILLNEED+SelDONTNEED (965) < WILLNEED alone (2521). Evicting pages reduces readahead effectiveness.
4. **256MB vs 512MB FADVISE**: At 512MB, blanket FADVISE was -17x (evicting useful hot pages). At 256MB, it's neutral (page cache too small to help anyway).
5. **WILLNEED 256MB > baseline 512MB**: 2521 vs 2309 QPS. Kernel readahead more efficient than passive page cache.

### DEEP10M WILLNEED 验证 (2026-08-04, CON-SLA-014)

| 配置 | QPS | Recall | RSS | refault | majfault | peak | file | max_events |
|------|-----|--------|-----|---------|----------|------|------|------------|
| 2GB base | 570 | 95.05% | 1157MB | 248 | 68152 | 2GB | 857MB | 11846 |
| 2GB +WILLNEED | 568 | 95.05% | 1156MB | 208 | 68707 | 2GB | 740MB | 12106 |

**结论：WILLNEED 在 DEEP10M 上中性**（-0.4%，无显著差异）
- pread 延迟降低（21ms->12ms），但 QPS 不变
- majfault 不变（68K）-- I/O 量是瓶颈，不是 I/O 时序
- cgroup 强制执行：peak=2GB, oom=0

### WILLNEED 适用条件总结

| 场景 | page cache 状态 | pread 是否瓶颈 | WILLNEED 效果 |
|------|----------------|---------------|------------|
| SIFT1M 256MB | 严重不足 | 是（8ms/query） | **17.7x** |
| SIFT1M 512MB | 充裕 | 否（4.8ms但热态快） | +5.5% |
| DEEP10M 2GB | 不足但I/O量主导 | 否（I/O量68K） | ~0% |

**WILLNEED 有效的条件**：
1. page cache 严重受限（budget << hot working set）
2. pread 是 query 延迟的主要来源
3. refault 暴涨证明 LRU 在误杀热页

DEEP10M 不满足条件 2：瓶颈是 majfault 总量（68K次磁盘读），不是 readahead 时序。

| cgroup | WILLNEED | QPS | Recall | RSS | refault | majfault | file | vs base |
|--------|----------|-----|--------|-----|---------|----------|------|--------|
| 512MB | OFF | 2408 | 95.75% | 155MB | 0 | 0 | 180MB | baseline |
| 512MB | ON | **2498** | 95.75% | 155MB | 0 | 0 | 136MB | **+3.7%** |

**结论：512MB 无回归** ✅
- QPS +3.7%（微正，不退化）
- Recall/RSS/refault/majfault 全部不变
- file 从 180MB 降到 136MB（WILLNEED 更精准的预取使用更少 page cache）
- pread 延迟：9522us -> 3643us（n=200），4812us -> 1875us（n=400）

### WILLNEED 跨 cgroup 对比

| cgroup | WILLNEED | QPS | pread(n=400) | refault | majfault |
|--------|----------|-----|-------------|---------|----------|
| 256MB | OFF | 136 | 8161us | 27439 | 5103 |
| 256MB | ON | 2521 | 1872us | 0 | 5039 |
| 512MB | OFF | 2408 | 4812us | 0 | 0 |
| 512MB | ON | 2498 | 1875us | 0 | 0 |

**核心洞察**：WILLNEED 使 256MB 达到 512MB 同等性能。pread 延迟在两种 cgroup 下几乎相同（1872us vs 1875us），说明内核 readahead 不受 cgroup 限制影响。

| date | round | cgroup | flat_vec | QPS | refault | majfault | note |
|------|-------|--------|----------|-----|---------|----------|------|
| 2026-08-03 | R4-4M | 256MB | 4MB | 139 | 27666 | 5105 | +flat_vec check in rerank |
| 2026-08-03 | R4-8M | 256MB | 8MB | 216 | 16414 | 5043 | |
| 2026-08-03 | R4-16M | 256MB | 16MB | 464 | 6888 | 4997 | |
| 2026-08-03 | R4-32M | 256MB | 32MB | 621 | 5339 | 4901 | |
| 2026-08-03 | R4-64M | 256MB | 64MB | 947 | 4048 | 5119 | 7.5x vs 基线 |
| 2026-08-03 | R4-512M | 512MB | 4MB | 2326 | 32 | 9 | 512MB 下无显著收益 |
