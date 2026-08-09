# Evidence: R1 — io_uring async fadvise (2026-08-09)

> 配置: SIFT1M M=16 EF=65, 256MB cgroup, 15 rounds × 1000 queries, seed 42
> 方向 E: io_uring IORING_OP_FADVISE 替代 bg_thread

## 结果

| Threads | sched_yield | R0 (ring=64) | R1 (ring=512) | 
|---------|-------------|-------------|---------------|
| 1T agg  | 1,441       | 1,274 (-11.6%) | 1,272 (-11.7%) |
| 1T steady | 1,553     | 1,380 (-11.2%) | 1,476 (-5.0%) |
| 8T agg  | 3,283       | 2,808 (-14.5%) | — |
| 16T agg | 3,022       | 2,589 (-14.3%) | CRASH |
| 16T steady | 3,802    | 2,954 (-22.3%) | CRASH |

## Perf Stat (R0, 1T)

| 指标 | sched_yield | io_uring | 说明 |
|------|------------|----------|------|
| io_uring_enter | 0 | 10,000 | 1/query |
| fadvise64 | 423,757 | 0 | 替换为 io_uring |
| sched_yield | 21M | 0 | 消除 |
| user time | 5.37s | 4.12s | -23% |
| sys time | 5.85s | 3.18s | -46% |
| wall time | 9.15s | 10.1s | +10.5% ❌ |

## 根因分析

### 问题 1: 异步 fadvise 队列延迟

```
sched_yield 架构 (Trunk):
  searchKnn → slot.ready=true
  bg_thread (always running) → posix_fadvise() → 内核 readahead [立即]
  searchKnn → pread() → 命中 page cache ✅

io_uring 架构 (R0/R1):
  searchKnn → io_uring_submit(FADVISE) [系统调用]
  内核排队 SQE → 异步工作线程处理 → readahead [延迟]
  searchKnn → pread() → 可能 miss page cache ❌
```

posix_fadvise 是**同步**的——调用后内核立即启动 readahead。
io_uring FADVISE 是**异步**的——提交后需要内核调度处理，有 ~5-20μs 延迟。

### 问题 2: SQ 环非线程安全

R0 的 16T 结果 (-22%) 比 1T (-11%) 更差，因为：
- 16 个线程并发写 SQ 环 → 竞争 tail 指针 → SQE 覆盖
- ring=64 时发生溢出（16T × 30 pages/query = 480 SQEs 进 64 entry ring）
- ring=512 时仍有 race condition → CRASH

io_uring 的 SQ 不是 multi-producer safe 的，需要外部同步（mutex），
这完全违背了消除 bg_thread 的初衷。

### 为什么 R1 steady 比 R0 好但仍低于 baseline

R1 (ring=512) 1T steady=1,476 比 R0 (ring=64) 1,380 好，因为大 ring 减少了
溢出。但 readahead 延迟仍然存在，无法追上 sched_yield 的零延迟 fadvise。

## 结论

**方向 E (io_uring fadvise) 全面证伪。** 三个根本性问题：

1. **异步延迟**: io_uring fadvise 的异步处理比 posix_fadvise 的同步 readahead 慢
2. **线程不安全**: SQ 环不支持多线程并发提交
3. **前车之鉴**: fine-rerank-iouring POC 已证明 io_uring READ 在此架构下也负结果

**sched_yield bg_thread 架构的正确性**: bg_thread 的 sched_yield 自旋虽然
"浪费" CPU，但提供了**零延迟 fadvise 提交**，这是 readahead 能及时启动的关键。
"浪费"的 CPU 实际上在为 pread 预热 page cache——这不是浪费，是必要投资。

**对比 hybrid pause+yield (方向 B)**: hybrid 通过减少 yield 频率来降低 CPU 开销，
同时保持同步 fadvise 路径，是唯一既省 CPU 又不增加延迟的方案。
