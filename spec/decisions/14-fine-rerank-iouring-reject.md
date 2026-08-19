# Decisions - Fine Rerank io_uring POC (DEC-076)

> 条款索引: `DEC-076`

## D-076: Fine Rerank io_uring 替代 WILLNEED_BG+pread 负结果 {#DEC-076}
<!-- ndf: kind=decision status=stable date=2026-08-06 affects=BEH-027,BEH-024 source=observed -->
<!-- ndf: depends-on=DEC-070,DEC-074,BEH-024,BEH-027 -->

**Context.** fine-rerank-iouring POC 探索用 per-thread io_uring (buffered) 替代
WILLNEED_BG + pread 的 Fine Rerank I/O 路径。R5c mincore 诊断显示 87.9% 的
vecblocks 页不在 page cache 中, 这些页必须走磁盘 I/O。

4 种方案在 256MB cgroup (page cache 紧张) 和 512MB cgroup (page cache 充裕) 下测试:

| 方案 | 256MB QPS | vs 基线 | 机制 |
|------|-----------|---------|------|
| R0 (WILLNEED_BG+pread) | 2,807 | 基线 | BG fadvise ∥ pread (天然并行) |
| R1 (纯 io_uring) | 2,493 | -11.2% | io_uring 显式读, 无 readahead |
| R2 (串行混合) | 2,779 | -1.0% | fadvise -> io_uring (串行) |
| R3 (异步并行) | 2,622 | -6.6% | BG fadvise ∥ io_uring (竞态) |

**根因分析:**

1. **R1 负原因**: io_uring 显式读不享受 fadvise(WILLNEED) 触发的内核 readahead
   优化 (I/O 合并/调度/自适应预读窗口)。majfault 比 R0 多 13% (256MB)。

2. **R2 持平原因**: 串行 fadvise 先全部完成再 io_uring, 所有页享受 readahead。
   但 fadvise+io_uring 产生重复 I/O (majfault 比 R0 多 24%), 抵消完成顺序处理优势。

3. **R3 负原因**: BG fadvise 和 io_uring 竞态 -- 部分页 io_uring 先到 (无 readahead),
   部分页两者同时 (重复 I/O)。majfault 最高 (比 R0 多 33%)。

4. **R0 最优根因**: pread 从 page cache 读是"被动"的 -- readahead 完成则命中,
   未完成则阻塞, **不产生重复 I/O**。BG 线程 fadvise 和 pread 天然并行, 无需 io_uring。

**Decision.**

1. **确认 WILLNEED_BG + pread 为 Fine Rerank I/O 最优架构。** io_uring (buffered)
   在所有测试配置下均不优于 pread。

2. **不引入 FINE_IOURING 路径。** POC 代码保留在 `poc/fine-rerank-iouring/` 供参考,
   不合入 Trunk。

3. **P3 (100M) 可重新评估。** page cache 完全失效时, readahead 优势消失,
   io_uring + O_DIRECT 可能成为替代方案。

**Alternatives rejected.**
- 纯 io_uring (R1): -11.2% QPS, 无 readahead 优化
- 串行混合 (R2): 持平但有重复 I/O, 无净收益
- 异步并行 (R3): -6.6% QPS, fadvise/io_uring 竞态

> rationale: io_uring 的显式读与 fadvise 的 readahead 产生重复 I/O,
> 而 pread 的被动读不会。这个根本差异使得 io_uring 无法超越 pread + fadvise 组合。
> 内核 readahead 的 I/O 调度优化 (合并/重排/预读窗口) 在 page cache 受限时
> 仍有价值 (12% 覆盖率下 majfault 差异 13%)。

- refines: [[BEH-027]]
- verifies: POC fine-rerank-iouring R0-R3
