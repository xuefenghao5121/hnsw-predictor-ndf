# Proposal: POC — WILLNEED_BG futex 替换 sched_yield

> track: poc
> status: proposal
> 日期: 2026-08-09
> 关联: BEH-027 (WILLNEED_BG 行为), DEC-074 (A2 lockless bg 决策)

## 背景

Trunk profiling (SHA=4697c0d, SIFT1M 256MB 1T) 显示：

- WILLNEED_BG 后台线程的 sched_yield 自旋消耗 ~18.4% P-core CPU
- 每 query 2,116 次 sched_yield，但实际仅 42 次 fadvise（50:1 空转比）
- bg_thread 扫描 128 个 slot（MAX_THREADS），1T 场景仅 1 个活跃
- WILLNEED_BG=0 (inline fadvise) 测得 -12.1% QPS，确认 bg_thread 有价值

## 假设

将 bg_thread 的 `std::this_thread::yield()` (sched_yield) 替换为 futex 阻塞/唤醒机制，
可以消除 ~18% CPU 空转开销，同时保持 fadvise 提交的及时性。

## 设计

### 当前架构 (sched_yield)

```
bg_thread: while(1) { 扫描128 slot → fadvise → sched_yield }
searchKnn: slot.ready = true → 继续 pread (不等)
```

### 提议架构 (futex)

```
bg_thread: while(1) { 扫描 slot → fadvise → futex_wait(无工作时阻塞) }
searchKnn: slot.ready = true → futex_wake(bg_thread) → 继续 pread
```

关键设计点：
1. **保留 SPSC slot 结构** — 不改 searchKnn → bg_thread 的通信路径
2. **wake 粒度**：searchKnn 在 `slot.ready = true` 后调用 `futex_wake`，唤醒 bg_thread
3. **bg_thread 空闲判定**：扫完所有 slot 无工作 → futex_wait（而非 yield）
4. **1T 场景扫描范围**：动态限制为 `min(MAX_THREADS, active_slots)`（方向 A 合入）
5. **多线程兼容**：多 searchKnn 线程可能并发 wake，futex_wake 是线程安全的

### 唤醒延迟分析

| 指标 | sched_yield (当前) | futex (提议) |
|------|-------------------|-------------|
| fadvise 提交延迟 | ~0μs (线程在 spin) | ~1-5μs (futex_wake → schedule) |
| CPU 开销 | 18.4% (空转) | ~0% (阻塞) |
| 每 query 延迟 | 600μs | 600μs + ~5μs = 605μs |
| 延迟增加 | — | +0.83% (可忽略) |

## 实现计划

1. 在 `poc/bg-thread-futex/` 中实现 futex 版 bg_thread
2. 对比测试 (256MB 1T, EF=65)：
   - baseline: WILLNEED_BG=1 (sched_yield)
   - R0: futex + dynamic slot scan
   - R1: 如 R0 正向，测试不同 wake 策略
3. perf record 对比 CPU 分布

## 验证标准

- QPS ≥ baseline (1,441 agg / 1,553 steady)
- Recall = 95.52% (不变)
- sched_yield 计数 < 1,000（从 21M 降至近 0）
- bg_thread CPU 占比从 14.6% 降至 < 2%

## 约束

- 仅改 `poc/bg-thread-futex/`（[[CON-POC-001]]）
- 不修改 Trunk `src/`、`include/`、`tests/`
- 测试协议: N=1000 R=15 seed=42, 1T, 256MB cgroup
