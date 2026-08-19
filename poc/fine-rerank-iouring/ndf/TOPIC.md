# TOPIC: fine-rerank-iouring

> topic_id: fine-rerank-iouring
> status: rejected (2026-08-06: R1-R3 全部负结果, WILLNEED_BG+pread 确认为最优架构)
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

### R0+R1 结果 (2026-08-06)

**256MB cgroup (page cache 紧张):**

| 指标 | R0 (WILLNEED+pread) | R1 (io_uring) | 差异 |
|------|---------------------|---------------|------|
| QPS | 2,656 | 2,224 | -16.2% ❌ |
| Recall | 95.80% | 95.80% | ✅ 一致 |
| Mean | 0.38ms | 0.45ms | +18% |
| majfault | 26,222 | 33,582 | +28% |
| refault | 3,494 | 5,055 | +45% |
| I/O 时间 | pread=1852us | submit+wait=470us | io_uring 4x 快 |

**512MB cgroup (page cache 充裕):**

| 指标 | R0 (WILLNEED+pread) | R1 (io_uring) | 差异 |
|------|---------------------|---------------|------|
| QPS | 3,233 | 3,173 | -1.9% (噪声) |
| Recall | 95.75% | 95.75% | ✅ 一致 |
| majfault | 33,586 | 33,625 | ≈0% |
| I/O 时间 | pread=1890us | submit+wait=414us | io_uring 4x 快 |

### 负结果根因分析

1. **io_uring I/O 执行更快但 majfault 更多**: io_uring submit+wait (414-470us) 比 pread loop (1852-1890us) 快 4x，但 majfault 多 28% (256MB)。总 QPS 仍低。
2. **根因: fadvise(WILLNEED) 触发内核 readahead 优化**: 内核 readahead 可以 I/O 合并、调度、自适应预读窗口。io_uring 显式读走不同代码路径，不享受这些优化。
3. **512MB 下差异消失**: page cache 充裕时，大多数页已在 cache，readahead 优势不明显。
4. **完成顺序处理优势被 readahead 劣势抵消**: 虽然按 CQE 完成顺序处理更快，但更多 majfault 导致总延迟更高。

### 结论

**WILLNEED_BG + pread 是正确的架构选择。** 内核 readahead 的优化能力难以被显式 io_uring 匹配，尤其在 page cache 受限场景。

### 可能的后续方向 (未验证)

- ~~io_uring + fadvise 混合~~: R2 串行混合持平基线 (-1.0%), R3 异步并行更差 (-6.6%)
- P3 (100M) 规模重新评估: page cache 完全失效时, readahead 优势消失, io_uring 可能持平或胜出

### R2+R3 补充结果 (2026-08-06)

**256MB cgroup (4 方案完整对比):**

| 方案 | QPS | vs R0 | iouring 总时间 | majfault |
|------|-----|-------|---------------|----------|
| R0 (WILLNEED_BG+pread) | 2,807 | 基线 | pread=1877us | 57,653 |
| R1 (纯 io_uring) | 2,493 | -11.2% | 471us | 65,017 |
| R2 (串行混合) | 2,779 | -1.0% | 342us | 71,752 |
| R3 (异步并行) | 2,622 | -6.6% | 336us | 76,955 |

### R3 负结果根因

R3 中 BG 线程 fadvise 和搜索线程 io_uring 同时执行, 产生竞态:
- 部分页: fadvise 先到 -> readahead -> io_uring 命中 cache (快)
- 部分页: io_uring 先到 -> 直接磁盘读 (慢, 无 readahead)
- 部分页: 两者同时 -> 重复 I/O (majfault 最高)

R2 串行混合中 fadvise 先全部完成再 io_uring, 所有页享受 readahead, 所以 R2 > R3.

### 最终结论

**WILLNEED_BG + pread 确认为最优架构。** 四种方案 (R0-R3) 中 R0 性能最佳:
1. BG 线程 fadvise 和 pread 天然并行, 无需 io_uring
2. pread 从 page cache 读, 不产生重复 I/O (不像 io_uring 会与 readahead 冲突)
3. 内核 readahead 优化 + pread cache 命中的组合最优
4. io_uring 的完成顺序处理优势被重复 I/O 和缺乏 readahead 优化抵消

## Next gate

- [x] R0: 确认基线 (WILLNEED_BG + pread) -> 256MB: 2656 QPS, 512MB: 3233 QPS
- [x] R1: per-thread io_uring (buffered) -> 256MB: 2224 QPS (-16%), 512MB: 3173 QPS (-2%)
- [ ] R2: io_uring + page merge (跳过, R1 已否定)
- [ ] R3: io_uring + 完成顺序处理 (已在 R1 实现, 无收益)
- [ ] R4: 16T 并发验证 (跳过, R1 已否定)
- [ ] R5: 512MB 回归 -> 已在 R1 中完成
- [ ] R6: DEEP10M 验证 (跳过)
- [x] 决策: **reject** - R1-R3 全部负结果, WILLNEED_BG+pread 确认为最优架构
- [x] R2: 串行混合 fadvise+io_uring -> 2779 QPS (-1.0%, 持平基线)
- [x] R3: 异步并行 BG fadvise + io_uring -> 2622 QPS (-6.6%, 竞态导致更差)

## Draft clauses

_(none — topic rejected; IDs never entered Trunk)_

## Rejected / absent clauses

| ID | In spec/? | Notes |
|----|-----------|-------|
| BEH-029 | no (absent) | Fine Rerank io_uring 路径 — rejected with topic |
| API-014 | no (absent) | FINE_IOURING env — rejected with topic |
| DEC-076 | yes (reject DEC) | per-thread io_uring vs WILLNEED_BG 负结果 |

## Proposals

| Role | Path | Status |
|------|------|--------|
| root | `ndf/proposals/proposal-fine-rerank-iouring.md` | Rejected |

## Evidence

(待实验)

## Commits

见 [COMMITS.md](COMMITS.md)
