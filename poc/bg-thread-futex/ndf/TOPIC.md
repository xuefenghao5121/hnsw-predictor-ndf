# TOPIC: bg-thread-futex

> topic_id: bg-thread-futex
> status: rejected (all directions explored; hybrid pause+yield 无严格 A/B 收益)
> opened: 2026-08-09
> closed: 2026-08-09
> depends_on_topics: multi-thread-scaling (promoted, A2 lockless bg baseline)
> baseline_trunk_sha: 4697c0d
> baseline_status: current
> explore_surface: io-path,willneed-bg,thread-sync

## 假设

将 WILLNEED_BG 的 sched_yield 自旋替换为 futex/ io_uring/ pause+yield，
消除 ~18.4% P-core CPU 空转，预期 +15-17% QPS (1T 256MB)。

## 结论

| 方案 | 1T steady | 16T steady | 严格 A/B | 结论 |
|------|----------|-----------|---------|------|
| D: futex | -4.6%* | +2.5%* | n/a | 证伪: wake 延迟 |
| E: io_uring | -11.2%* | -22.3%* | n/a | 证伪: async delay + race |
| B: hybrid pause+yield | +4.8%* | +5.1%* | **-0.1~-0.3%** | **证伪: 严格 A/B 无收益** |

*非严格 A/B，有系统性偏差

严格 A/B 对比（同一 session、同一环境、alternating runs）：
| Config | Old agg | New agg | Δ steady |
|--------|---------|---------|----------|
| EF=100 1T | 1,072 | 1,064 | -0.2% |
| EF=65 1T | 1,473 | 1,456 | -0.1% |
| EF=65 16T | 3,186 | 3,087 | -0.3% |

hybrid pause+yield 在严格 A/B 下无正向收益，之前 +4.8%/+5.1% 是测量偏差。

## 根因

bg_thread 的 sched_yield 自旋看似浪费 CPU，实际不影响关键路径性能：
1. fadvise 提交延迟由 posix_fadvise 本身决定，与 yield 频率无关
2. pread 延迟由内核 readahead + 磁盘 I/O 决定
3. yield 的 CPU 开销与 16 个搜索线程并发时不是瓶颈
4. _mm_pause × 8 ≈ 80ns，对 ~1μs 的 sched_yield 影响可忽略

## 提案

- `spec/open/proposal-poc-bg-thread-futex.md` (rejected)
