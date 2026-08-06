# fine-rerank-iouring - POC 笔记

> 提案: `ndf/proposals/proposal-fine-rerank-iouring.md`
> 基线: Trunk 476b953 (WILLNEED_BG + PAGE_MERGE_BG + VL_POOL)
> 协议: [[CON-SLA-014]] + [[CON-SLA-016]] + [[CON-SLA-018]]
> 状态: 待开题审核

## 核心问题

当前 WILLNEED_BG + pread 路径:
1. BG 线程 yield 轮询 -> fadvise N 次 syscall -> 内核 readahead -> pread N 次
2. pread 固定顺序阻塞, 无法按完成顺序处理
3. 每查询 2N syscall (N=fadvise + N=pread)

per-thread io_uring (buffered):
1. 1 次 io_uring_submit -> 内核立即并行读 -> CQE 完成通知
2. 按完成顺序处理 (先到先算距离)
3. 每查询 1 syscall

## 关键设计决策

### buffered 模式 (非 O_DIRECT)

- 页进 kernel page cache -> 跨 query 复用不变
- 与 pread 的 page cache 行为一致
- 不丢失 12.1% 的热页命中

### per-thread 实例

- 每搜索线程一个独立 IoUring (256 entries × 8KB = 2MB)
- 无共享状态 -> 无锁 -> 无竞争
- 16T = 32MB 额外内存, 256MB cgroup 下可接受

### 替代 (非叠加)

- io_uring 完全替代 WILLNEED_BG + pread
- 不叠加 WILLNEED (io_uring 自身就是预取机制)
- FVC 仍然在前 (io_uring 只处理 FVC miss 的候选)

## 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| FINE_IOURING | 启用 io_uring 路径 | 0 (关闭) |
| 与 FINE_PREAD | 互斥 | - |
| 与 L4_WILLNEED / WILLNEED_BG | 互斥 | - |

## 实验计划

| 轮次 | 配置 | 目标 | 状态 |
|------|------|------|------|
| R0 | 基线 (WILLNEED_BG + pread) | 确认基线 | pending |
| R1 | per-thread io_uring (buffered) | 核心对比 | pending |
| R2 | io_uring + page merge | 减少 syscall | pending |
| R3 | io_uring + 完成顺序处理 | 验证乱序收益 | pending |
| R4 | 16T 并发 | 多线程扩展性 | pending |
| R5 | 512MB 回归 | 确认无回归 | pending |
| R6 | DEEP10M 2GB | 大数据集 | pending |

## 晋升条件

- 256MB 16T QPS 提升 >5%
- 512MB 无回归 (QPS 变化 ±2% 内)
- Recall 不变 (≥95%)
- 16T 线程安全稳定运行
