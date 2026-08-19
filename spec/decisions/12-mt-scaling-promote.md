# Decisions - 多线程拓展性优化 (DEC-074)

> 条款索引: `DEC-074`

## D-074: WILLNEED 后台线程化 + VisitedList 池化 {#DEC-074}
<!-- ndf: kind=decision status=stable date=2026-08-05 affects=BEH-024,BEH-027,API-013,CON-SLA-017 source=observed -->
<!-- ndf: depends-on=DEC-070,DEC-073,CON-SLA-014 -->

**Context.** multi-thread-scaling POC 发现 12T+ 性能瓶颈：
1. `posix_fadvise(WILLNEED)` 内核锁竞争 6.27% (osq_lock + queued_spin_lock + down_read)
2. VisitedList memset 10.29% (1MB memset per search, cache bouncing)

**优化探索** (6 个方向):
- A1 (mutex 后台线程): 512MB 8T -29% (mutex 引入新瓶颈)
- A2 (无锁后台线程): 512MB 16T +72.8%, 256MB 12T +61.3% ✅
- B (自适应禁用): 仅 12T +6.7%, 16T+ 灾难 (-38%) ❌
- C1 (always-on 池化): 4T -15.6% (thread_local 开销) ❌
- C2 (自适应池化): 12T +7.1%, 16T +6.0%, 低 T 零退化 ✅
- A3 (页合并): 512MB 16T+ -33% (排序开销) ❌

**Decision.** Promote A2 (WILLNEED_BG=1) + C2 (VL_POOL_THREADS=14):
- A2: SPSC per-thread slot + atomic flag + 后台轮询线程, 零 mutex
- C2: 自适应 VL_POOL, T≥阈值时启用 thread_local 复用
- 两者均为 opt-in 环境变量，默认不影响现有行为

**Consequences.**
- 512MB 16T peak: 30,332 QPS (hnswlib 73.3%, 内存效率 1.05x)
- 256MB 16T peak: 16,873 QPS (hnswlib 42.9%, 内存效率 1.17x)
- 新增 BEH-027, API-013, CON-SLA-017

**Promotes**: multi-thread-scaling
