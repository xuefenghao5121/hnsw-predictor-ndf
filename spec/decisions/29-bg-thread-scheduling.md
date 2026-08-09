# DEC-093: bg_thread 调度策略选型 — hybrid pause+yield

> 日期: 2026-08-09
> 关联: BEH-027, DEC-074
> Promotes: bg-thread-futex (partial)
> source: poc/bg-thread-futex/ndf/evidence/r0-scaling-sweep-20260809.md, r1-iouring-fadvise-20260809.md

## 背景

Trunk profiling (SHA=4697c0d) 显示 WILLNEED_BG 的 `sched_yield` 自旋消耗 ~18.4% P-core CPU（2,116 次/query）。POC `bg-thread-futex` 系统性评估了 4 种替代方案。

## 决策

采纳 **hybrid pause+yield**：在 `sched_yield()` 前插入 8x `_mm_pause()`（~100ns）。

| 方案 | 1T steady | 16T steady | 结论 |
|------|----------|-----------|------|
| sched_yield (旧 Trunk) | 1,553 | 3,802 | baseline |
| futex block/wake | -4.6% | +2.5% | **证伪**: futex wake 延迟 (~5-10μs) 导致 fadvise 提交滞后，pread 命中冷页 |
| io_uring async FADVISE | -11.2% | -22.3% | **证伪**: 异步队列延迟 + SQ 环非线程安全 |
| **hybrid pause+yield** | **+4.8%** | **+5.1%** | **采纳**: 全场景帕累托改进 |

## 根因

`posix_fadvise(WILLNEED)` 是同步的——调用即触发内核 readahead。bg_thread 的 sched_yield 自旋虽然"浪费" CPU，但保证了 fadvise 的零延迟提交，使 searchKnn 的 pread 能命中 page cache。

- futex 替换 yield 引入 wake 延迟 → fadvise 提交晚 5-10μs → readahead 未完成 → pread 冷读
- io_uring FADVISE 异步队列延迟更长 + SQ ring 不支持多线程并发写
- `_mm_pause` 是 CPU 级别的自旋提示（不浪费执行资源），减少 yield 频率但不增加 fadvise 延迟

## 代码变更

`src/core/disk_hnsw.cpp`：bg_thread 循环中 `yield()` 前插入 8x `_mm_pause()`。

## 验证

SIFT1M M=16 EF=65, 256MB cgroup, 15R×1000Q seed=42:

| 配置 | 旧 sched_yield | 新 hybrid | delta |
|------|--------------|-----------|-------|
| 1T steady | 1,553 | 1,627 | +4.8% |
| 8T steady | 4,079 | 4,089 | +0.2% |
| 16T steady | 3,802 | 3,995 | +5.1% |
| recall | 95.52% | 95.52% | 不变 |
