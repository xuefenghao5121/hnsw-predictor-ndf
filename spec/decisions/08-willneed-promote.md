# Decisions - WILLNEED Promote (DEC-070)

> 条款索引: `DEC-070`

## D-070: WILLNEED readahead hint promote {#DEC-070}
<!-- ndf: kind=decision date=2026-08-04 affects=BEH-024,API-012 source=observed -->
<!-- ndf: depends-on=DEC-068,CON-SLA-014,BEH-025 -->
<!-- ndf: promotes=l4-cache-mgmt-r5 -->

**Context.** L4 POC R5 实验发现，在 fine rerank pread 循环前对 `pages_needed` 调用
`posix_fadvise(POSIX_FADV_WILLNEED)`，可让内核启动异步 readahead，将串行 pread
转为流水线 I/O。

CON-SLA-014 标准协议验证结果：

| 场景 | cgroup | 基线 QPS | +WILLNEED | 提升 | refault(基线->WILLNEED) | majfault |
|------|--------|---------|-----------|------|------------------------|----------|
| SIFT1M | 256MB | 134 | 2379 | 17.7x | 27718->74 | 5102->5134 |
| SIFT1M | 512MB | 2267 | 2392 | +5.5% | 0->0 | 6->6 |
| DEEP10M | 2GB | 570 | 568 | ~0% | 248->208 | 68152->68707 |

cgroup 合规性验证：
- `memory.peak` = cgroup limit（所有场景均达到上限，从未超过）
- `oom` = 0（所有场景）
- `memory.events: max` > 0（cgroup 回收在生效）
- `file` 在预算内（256MB: 103MB = 256-153 RSS = 103MB budget）
- `majfault` 不变（WILLNEED 不减少磁盘 I/O 量，仅改变时序）

**Decision.** 将 WILLNEED readahead hint 合入 Trunk `src/`，作为 opt-in 环境变量
`L4_WILLNEED=1`（默认关闭）。BEH-024 扩展为包含 WILLNEED 段落（stable）。
API-012 新增（stable）。

**Consequences.**
- WILLNEED 在 page cache 严重受限场景下有显著收益（17.7x）
- 在其他场景下无副作用（+5.5% / ~0%）
- 不改 SLA 数字（opt-in 加速，非 must 要求）
- `L4_SELECTIVE_DONTNEED` 不 promote（保持 POC，R5b 仅 +14%）
- 不改 `FINE_FADVISE` 行为（保持现状）

**Non-goals.**
- 不 promote Selective DONTNEED（效果有限）
- 不改 SLA 数字
- 不改默认环境变量值
