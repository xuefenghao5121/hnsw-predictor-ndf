# Decisions - io-pipelining 负结果 (DEC-071)

> 条款索引: `DEC-071`

## D-071: io-pipelining 负结果关闭 {#DEC-071}
<!-- ndf: kind=decision date=2026-08-04 affects=BEH-021,BEH-022,BEH-023,API-010,CON-SLA-013 source=observed -->
<!-- ndf: rejects=io-pipelining depends-on=DEC-070,CON-SLA-014,BEH-020 -->

**Context.** I/O behavior correction 重测（CON-SLA-014 标准协议，DEEP10M 2GB/3GB）证实
`pipe_ring_`（BEH-021）在严格隔离下无收益。

CON-SLA-014 实测数据：

| 配置 | cgroup | PIPE_FINE | QPS | Recall | majfault | pipe_hits | 判定 |
|------|--------|-----------|-----|--------|----------|-----------|------|
| R0-base | 2GB | 0 | 563 | 95.05% | 69295 | 0 | 基线 |
| R1-pipe | 2GB | 1 | 558 | 95.05% | 69527 | 255 | -0.9% |
| R0-base | 3GB | 0 | 563 | 95.05% | 6 | 0 | 基线 |
| R1-pipe | 3GB | 1 | 553 | 95.05% | 6 | 255 | -1.8% |

pipe_ring_ 机械工作正常（pipe_hits=255 证明预取成功），但对 QPS 无贡献。

**Root Cause.** WILLNEED（DEC-070）已取代 pipe_ring_ 的价值。

DEC-070 promote 的 `posix_fadvise(WILLNEED)` 在 pread 循环前启动内核异步 readahead，
已实现 I/O 与 CPU 并行。pipe_ring_ 的预取与 WILLNEED 完全重叠——两者在同一时机
（Phase A 候选收集后、Phase B pread 前）触发。WILLNEED 使用内核 I/O 调度器
（批量合并、重排序），效率高于 pipe_ring_ 的用户态逐页提交。

历史背景：
- DEC-063（旧正结果）基于 EVICT_PAGE_CACHE 幽灵变量 + 未按 CON-SLA-014 清场，口径错误
- DEC-064（post-memopt 无收益）基于错误口径，但结论方向正确（pipe 无收益）
- 本 DEC 以 CON-SLA-014 标准协议确认：pipe_ring_ 在 WILLNEED 存在下无独立价值

**Decision.** 关闭 io-pipelining topic。以下条款 deprecated：

| ID | 原描述 | 废弃原因 |
|----|--------|---------|
| [[BEH-021]] | pipe_ring_ L5 预取 | WILLNEED 已覆盖同一 I/O 并行场景 |
| [[BEH-022]] | L1/L2/L3 CPU cache 预取 | 依附 BEH-021，无独立证据 |
| [[BEH-023]] | L4 page cache 旁路填充 | WILLNEED 直接填充 L4，更高效 |
| [[API-010]] | PIPE_* 环境变量 | 对应行为全部 deprecated |
| [[CON-SLA-013]] | I/O Pipelining SLA | 无有效行为可约束 |

**Consequences.**
- io-pipelining topic 关闭（TOPIC status=rejected）
- POC ndf 迁入 `spec/archive/2026-08/poc-io-pipelining/`
- pipe_ring_ 代码保留在 `poc/io-pipelining/`（不强制删除）
- Trunk `src/` 无需 revert（pipe_ring_ 从未合入）
- 未来 100M 规模若 I/O 瓶颈再现（WILLNEED 无法覆盖），可重新开题

**Trunk impact.** 无。所有 pipe 实现仅存在于 `poc/io-pipelining/`。
