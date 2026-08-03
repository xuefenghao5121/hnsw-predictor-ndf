# TOPIC: l4-cache-mgmt

> topic_id: l4-cache-mgmt
> status: exploring
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

- [ ] R4: 在 256MB cgroup 下测试选择性 DONTNEED / WILLNEED
- [ ] 目标：减少 refault（从 30326 向 <5000），抬升 QPS（从 126 向 500+）
- [ ] DEEP10M 严格隔离基线（天然 page cache 不足场景）

## Draft clauses

| ID | In spec/? | Notes |
|----|-----------|-------|
| [[BEH-024]] | yes (`status=draft`) | L4 主动管理；禁 EVICT 幽灵 |

## Proposals

| Role | Path | Status |
|------|------|--------|
| root | `spec/open/proposal-l4-cache-mgmt.md` | Implemented |

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
