# Proposal: 负结果闭环 - io-pipelining rejected {#PROP-REJECT-IO-PIPELINING}

> track: poc  
> Status: Implemented on 2026-08-04  
> 日期: 2026-08-04  
> Subject: io-pipelining topic 负结果闭环  
> 对齐: [[BEH-020]]  
> Rejects: io-pipelining  
> 关联: [[BEH-021]](draft), [[BEH-022]](draft), [[BEH-023]](draft), [[API-010]](draft), [[CON-SLA-013]](draft)

## 1. 根因

I/O behavior correction 重测（CON-SLA-014 标准协议，DEEP10M 2GB/3GB）证实：
`pipe_ring_`（BEH-021）在严格隔离下无收益。

| 配置 | cgroup | PIPE_FINE | QPS | Recall | majfault | pipe_hits | 判定 |
|------|--------|-----------|-----|--------|----------|-----------|------|
| R0-base | 2GB | 0 | 563 | 95.05% | 69295 | 0 | 基线 |
| R1-pipe | 2GB | 1 | 558 | 95.05% | 69527 | 255 | -0.9% |
| R0-base | 3GB | 0 | 563 | 95.05% | 6 | 0 | 基线 |
| R1-pipe | 3GB | 1 | 553 | 95.05% | 6 | 255 | -1.8% |

`pipe_ring_` 机械工作正常（pipe_hits=255），但对 QPS 无贡献。

**根因：WILLNEED (DEC-070) 已取代 pipe_ring_ 的价值。**

DEC-070 promote 的 `posix_fadvise(WILLNEED)` 在 pread 循环前启动内核异步 readahead，已实现 I/O 与 CPU 并行。pipe_ring_ 的预取与 WILLNEED 的预取完全重叠——两者在同一时机（Phase A 候选收集后、Phase B pread 前）触发。WILLNEED 使用内核 I/O 调度器（批量合并、重排序），效率高于 pipe_ring_ 的用户态逐页提交。

## 2. 废弃 ID 列表

| ID | 位置 | 当前 status | 动作 |
|----|------|------------|------|
| [[BEH-021]] | `20-behavior/search.md` | draft | **deprecated** |
| [[BEH-022]] | `20-behavior/search.md` | draft | **deprecated** |
| [[BEH-023]] | `20-behavior/search.md` | draft | **deprecated** |
| [[API-010]] | `30-interfaces/env.md` | draft | **deprecated** |
| [[CON-SLA-013]] | `40-constraints/sla.md` | draft | **deprecated** |

## 3. 提案状态变更

| 提案 | 动作 |
|------|------|
| `proposal-io-behavior-correction.md` | **Rejected**（目标达成：确认负结果） |
| `proposal-io-pipelining.md` | **Superseded** by 本提案 |

## 4. Trunk 确认

`pipe_ring_` 相关代码从未合入 `src/`。所有 pipe 实现仅存在于 `poc/io-pipelining/`。
无需 revert Trunk。

## 5. 归档

- `poc/io-pipelining/ndf/` 迁入 `spec/archive/2026-08/poc-io-pipelining/`
- `poc/io-pipelining/` 代码保留在 POC 目录（不强制删除）

## 6. 后续影响

- io-pipelining topic 关闭，释放对 BEH-021/022/023 的阻塞
- 未来 100M 规模若 I/O 瓶颈再现（WILLNEED 无法覆盖的场景），可重新开题
- `proposal-4t-scaling-investigation.md` 的 io-pipelining 依赖解除

## 7. 非目标

- 不删除 POC 代码（保留供未来参考）
- 不改写已推送历史
- 不改 Trunk `src/`
