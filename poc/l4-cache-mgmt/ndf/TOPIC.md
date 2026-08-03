# TOPIC: l4-cache-mgmt

> topic_id: l4-cache-mgmt
> status: exploring
> baseline_protocol: [[CON-SLA-014]] + SIFT1M 512MB cgroup；Buffered 1T ([[DEC-066]])
> depends_on_topics: (none; **this topic precedes** io-pipelining re-bench)
> binder: [[DEF-022]] / [[BEH-025]]

## Active hypothesis

严格隔离下 peak file 顶满导致内核盲目 LRU；对 vecblocks 做精准 DONTNEED / WILLNEED /
基于 `FINE_FADVISE` 的选择性驱逐，可抬升 Buffered QPS（aspirational ≥×1.5）。

## R0-R3 v2 结论 (2026-08-03)

**FINE_FADVISE 有害（-17x），L4_EVICT_META 微正（+3%）。** page cache 命中是 Fine I/O 瓶颈的关键杠杆。

### 核心数据

| 轮次 | 机制 | QPS | pread (热态) | file(end) | 结论 |
|------|------|-----|-------------|-----------|------|
| R0 | Buffered 基线 | 2309 | 4.8ms | 374MB | 基线 |
| R1 | +FINE_FADVISE (evict vecblocks) | 133 | 8.3ms | 370MB | ❌ 17x 下降 |
| R2 | +L4_EVICT_META (evict graph+BFS) | 2383 | 4.7ms | 181MB | ✅ +3% |
| R3 | +两者 | 132 | 8.2ms | 143MB | ❌ FADVISE 主导 |

### Profile 分解

- Phase A (PQ 粗筛)：负值（计时 bug 待修）
- **pread (Fine I/O)：9.4→4.8ms（热态，page cache 预热 2x）；FADVISE 破坏预热**
- rerank (L2 计算)：27-45μs（非瓶颈）
- **Fine I/O 占总延迟 95%+**

### 关键洞察

1. **page cache 对 vecblocks 跨 query 预热极其关键**：前 200q pread=9.4ms，后 200q pread=4.8ms
2. **FINE_FADVISE 驱逐 vecblocks 页 = 自毁长城**：阻止 page cache 跨 query 积累
3. **L4_EVICT_META 驱逐 graph 页 = 释放预算给 vecblocks**：file(end) 374→181MB，vecblocks 获得更多空间
4. **workingset_refault=0**：内核 LRU 未误杀热页，WILLNEED 无用武之地
5. **R0-R3 v1 全部作废**：PQ_CODES_PATH 拼写错误（少了个 S），PQ 未加载

### v1 作废说明

v1 脚本设 `PQ_CODE_PATH`（无 S），benchmark 读 `PQ_CODES_PATH`（有 S）。PQ 未加载导致走了无 PQ 粗筛的 fallback 路径，QPS=23（非真实基线）。修正后 QPS=2309。

## Next gate

- [ ] 决策：L4_EVICT_META (+3%) 是否值得 promote 为 Trunk 可选项
- [ ] 决策：FINE_FADVISE 在严格隔离下是否需要标注"有害"或改默认
- [ ] Phase A 计时 bug 修复（负值问题）
- [ ] 考虑：增大 flat_vec_cache / BlockCache 替代 page cache 管理

## Draft clauses

| ID | In spec/? | Notes |
|----|-----------|-------|
| [[BEH-024]] | yes (`status=draft`) | L4 主动管理；禁 EVICT 幽灵 |

## Proposals

| Role | Path | Status |
|------|------|--------|
| root | `spec/archive/2026-08/proposal-l4-cache-mgmt.md`（open stub） | Implemented |

## Evidence

| date | round | protocol | QPS | pread(热) | file(end) | note |
|------|-------|----------|-----|-----------|-----------|------|
| 2026-08-03 | R0 v2 | CON-SLA-014 512MB | 2309 | 4.8ms | 374MB | FINE_BUFFERED=1 baseline |
| 2026-08-03 | R1 v2 | 同上 | 133 | 8.3ms | 370MB | +FINE_FADVISE=1, ❌ 17x 下降 |
| 2026-08-03 | R2 v2 | 同上 | 2383 | 4.7ms | 181MB | +L4_EVICT_META=1, ✅ +3% |
| 2026-08-03 | R3 v2 | 同上 | 132 | 8.2ms | 143MB | +both, FADVISE 主导下降 |
| 2026-08-03 | R0-R3 v1 | 同上 | 23 | - | - | **作废**: PQ_CODES_PATH 拼写错误 |

## Commits

见 [COMMITS.md](COMMITS.md)
