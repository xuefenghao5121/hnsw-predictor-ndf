# TOPIC: bg-thread-futex

> topic_id: bg-thread-futex
> status: promoted (partial: hybrid pause+yield adopted; futex rejected for 1T; io_uring rejected)
> opened: 2026-08-09
> depends_on_topics: multi-thread-scaling (promoted, A2 lockless bg baseline)
> baseline_trunk_sha: 4697c0d
> baseline_status: current
> explore_surface: io-path,willneed-bg,thread-sync

## 假设

将 WILLNEED_BG 的 sched_yield 自旋替换为 futex 阻塞/唤醒，
消除 ~18.4% P-core CPU 空转，预期 +15-17% QPS (1T 256MB)。

## Baseline

| 配置 | Agg QPS | Steady QPS | Recall |
|------|---------|-----------|--------|
| EF=65 WILLNEED_BG=1 (sched_yield) | 1,441 | 1,553 | 95.52% |
| EF=65 WILLNEED_BG=0 (inline) | 1,266 | 1,394 | 95.52% |

Profiling: bg_thread 14.6% + sched_yield path ~3.8% = 18.4% P-core waste.

## 计划

- R0: futex_wait/wake 替换 sched_yield + dynamic slot scan
- R1: (如正向) 调优 wake 策略
- R2: (如需要) 多线程验证

## 提案

- `spec/open/proposal-poc-bg-thread-futex.md`
