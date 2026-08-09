# NOTES: bg-thread-futex

> status: rejected (all directions explored, no promote)
> 开题: 2026-08-09
> 关闭: 2026-08-09
> Trunk SHA: 4697c0d

## 结论

所有三个方向 (futex / io_uring / pause+yield) 均证伪。
sched_yield 自旋是当前架构的最优调度策略。
之前 POC 的"正向结果"是测量偏差，严格 A/B 对比下无收益。
