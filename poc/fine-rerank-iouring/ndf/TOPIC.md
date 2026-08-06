# TOPIC: fine-rerank-iouring

> topic_id: fine-rerank-iouring
> status: exploring
> baseline_protocol: [[CON-SLA-014]] + [[CON-SLA-016]] + [[CON-SLA-018]]
> baseline_trunk_sha: 476b953
> baseline_status: current
> explore_surface: fine-rerank,io-path
> depends_on_topics: l4-cache-mgmt (closed, provides baseline)
> conflicts_with_topics: io-pipelining (rejected, different approach)
> binder: [[DEF-022]] / [[BEH-025]]

## Active hypothesis

当前 Fine Rerank 的 WILLNEED_BG + pread 路径存在三个效率问题:
1. BG 线程轮询延迟 (yield -> detect -> N×fadvise)
2. pread 固定顺序阻塞 (无法按完成顺序处理)
3. syscall 数量过多 (2N/query)

R5c mincore 诊断显示 87.9% 的 vecblocks 页不在 page cache 中,
这些页必须走磁盘 I/O。用 per-thread io_uring (buffered) 替代可:
- 1 次 io_uring_submit 批量提交 (消除 BG 轮询延迟)
- 按完成顺序处理 (消除固定顺序阻塞)
- 保留 page cache 复用 (buffered 模式)

## 基线 (Trunk 476b953)

**SIFT1M 256MB (FVC=64, WILLNEED_BG=1, PAGE_MERGE_BG=1, VL_POOL_THREADS=14):**

| 线程数 | QPS | Recall |
|--------|-----|--------|
| 1T | 2,830 | 95.80% |
| 16T (peak) | 18,675 | 95.80% |

**SIFT1M 512MB (FVC=160, WILLNEED_BG=1, PAGE_MERGE_BG=1, VL_POOL_THREADS=14):**

| 线程数 | QPS | Recall |
|--------|-----|--------|
| 1T | 3,366 | 95.75% |
| 16T (peak) | 30,332 | 95.75% |

## R5c mincore 证据 (256MB)

- vecblocks page cache 命中率: 12.1%
- **87.9% 的页需磁盘 I/O**
- pgmajfault: 5,114 / 200 queries = ~25 页/query 真实磁盘 I/O
- refault_file: 725 (WILLNEED_BG 已消除容量缺失)
- 剩余 majfault 是冷缺失, 不可通过 L4 管理优化
- 但 I/O 路径效率可优化 (提交延迟 + 顺序阻塞 + syscall 数量)

## 实验进展

(尚未开始)

## Next gate

- [ ] R0: 确认基线 (WILLNEED_BG + pread)
- [ ] R1: per-thread io_uring (buffered) 1T 256MB
- [ ] R2: io_uring + page merge
- [ ] R3: io_uring + 完成顺序处理
- [ ] R4: 16T 并发验证
- [ ] R5: 512MB 回归
- [ ] R6: DEEP10M 验证
- [ ] 决策: promote 或 reject

## Draft clauses

| ID | In spec/? | Notes |
|----|-----------|-------|
| BEH-029 (draft) | no | Fine Rerank io_uring 路径行为 |
| API-014 (draft) | no | FINE_IOURING 环境变量 |
| DEC-076 (draft) | no | per-thread io_uring vs WILLNEED_BG 决策 |

## Proposals

| Role | Path | Status |
|------|------|--------|
| root | `ndf/proposals/proposal-fine-rerank-iouring.md` | draft |

## Evidence

(待实验)

## Commits

见 [COMMITS.md](COMMITS.md)
