# POC: I/O Pipelining - 统一多层预取架构

> 提案: `spec/open/proposal-io-pipelining.md` (r2)
> 关联: [[DEC-060]] 方向 2、[[BEH-021]]、[[BEH-022]]、[[BEH-023]]、[[API-010]]、[[CON-SLA-013]]
> track: poc | 创建: 2026-08-01 | 修订: 2026-08-01 (r2: 统一多层架构)

## 架构

```
Disk (NVMe)
    ↓ io_uring (O_DIRECT or Buffered)
L5: pipe_ring_ (~800KB, 单 query, thread_local)
    ↓
L4: Page Cache (cgroup_limit - RSS, ~240-390MB, 跨 query)
    ↓
L1/L2/L3: CPU Cache (~30MB L3, 单次计算)
```

所有层协作，不分模式分治。pipe_ring_ 两种模式都保留。

## 实现状态

### ✅ 已完成

- [x] Step 1: pipe_ring_ 基础设施 (L5) - thread_local IoUring, 4KB buffer pool
- [x] Step 2: 预取提交 (L5) - searchLayer0() PQ 路径 4 个 emplace 点
- [x] Step 3: L4 旁路填充 - pipe_ring_ 满时 readahead() (Buffered only)
- [x] Step 4: Phase B 对接 - pipe_ring_ reap + fallback to vec_ring_/pread
- [x] Step 5: L1/L2/L3 预取 - _mm_prefetch 下一个候选向量
- [x] 编译通过
- [x] Smoke test: baseline / PIPE_FINE / PIPE_FINE+O_DIRECT / PIPE_FINE+O_DIRECT+PIPE_L1

### Smoke Test 结果 (SIFT1M, 200 queries, ef=100, 1T, no cgroup)

| 配置 | Recall | QPS | RSS | 状态 |
|------|--------|-----|-----|------|
| baseline (PIPE_FINE=0) | 98.35% | 24.2 | 266MB | ✅ |
| PIPE_FINE=1 (Buffered) | 98.35% | 23.5 | 266MB | ✅ |
| PIPE_FINE=1 + O_DIRECT | 98.35% | 24.0 | 266MB | ✅ |
| PIPE_FINE=1 + O_DIRECT + PIPE_L1 | 98.35% | 23.4 | 266MB | ✅ |

> 200 query 样本太小，QPS 差异在噪声范围内。需 R0-R4 正式 benchmark。

### 待做

- [ ] R0-R4 正式 benchmark (cgroup + REFINE_EF + multithreaded)
- [ ] 完善 pipe_ring_ page->buf_idx 映射 (当前 O_DIRECT pipe_ring_ 命中未完全利用)
- [ ] PROFILE_PIPE 统计输出

## NOTES

- pipe_ring_ 是 `static thread_local`，多线程安全
- 与 `SPEC_PREFETCH=1` 可共存（不同层：block cache vs vecblocks 页）
- 不改 I/O 粒度（避免重蹈 [[DEC-061]]）
- 系统优化不是非此即彼，而是彼此依赖的层叠结构
- 当前 POC 的 pipe_ring_ reap 逻辑简化：O_DIRECT 模式下 pipe_ring_ 命中检测不完整
  （需要 page->buf_idx 映射），Buffered 模式下通过 page cache 自然命中
  正式 benchmark 需完善此映射以验证 O_DIRECT 收益
