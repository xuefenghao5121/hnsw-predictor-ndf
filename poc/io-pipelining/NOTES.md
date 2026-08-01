# POC: I/O Pipelining - 统一多层预取架构

> 提案: `spec/open/proposal-io-pipelining.md` (r2)
> 关联: [[DEC-060]] 方向 2、[[BEH-021]]、[[BEH-022]]、[[BEH-023]]、[[API-010]]、[[CON-SLA-013]]
> track: poc | 创建: 2026-08-01 | 修订: 2026-08-01 (r2: 统一多层架构)

## 架构

```
Disk (NVMe)
    ↓ io_uring (O_DIRECT or Buffered)
L5: pipe_ring_ (~800KB, 单 query)
    ↓
L4: Page Cache (cgroup_limit - RSS, ~240-390MB, 跨 query)
    ↓
L1/L2/L3: CPU Cache (~30MB L3, 单次计算)
```

所有层协作，不分模式分治。pipe_ring_ 两种模式都保留。

## 实现计划

### Step 1: pipe_ring_ 基础设施 (L5)
- 新增 `thread_local IoUring pipe_ring_`（独立于 `vec_ring_`）
- buffer pool: ~200 个 4KB 对齐 slot
- 初始化时机：`buildFineRerank()` 成功后
- O_DIRECT: `pipe_ring_` 以 O_DIRECT 提交
- Buffered: `pipe_ring_` 以 buffered I/O 提交（自然填充 L4）

### Step 2: 预取提交 (L5)
- `searchLayer0()` 核心循环中，候选加入 `top_candidates` 后：
  1. 计算 `vec_route_table_[nid]` -> page0 偏移
  2. 去重检查（`unordered_set<uint32_t> piped_pages_`）
  3. rank ≤ `PIPE_THRESHOLD` 时提交 `pipe_ring_->submitReadNF()`
  4. cross-page 候选提交两个 SQE

### Step 3: L4 旁路填充 (可选)
- Buffered 模式下，pipe_ring_ buffer 满时 `readahead()` 旁路填充 page cache
- O_DIRECT 模式下此开关无效

### Step 4: Phase B 对接
- 先 reap pipe_ring_ 已就绪页 (L5)
- 再查 page cache (L4, Buffered 模式)
- 最后 vec_ring_ 同步 I/O (miss)
- 遍历候选时 _mm_prefetch 下一个向量到 L1/L2/L3

### Step 5: L1/L2/L3 预取
- Phase B 遍历候选前，`_mm_prefetch` 下一个候选的向量
- 粒度: `ceil(dim * sizeof(float) / 64)` 条 cache line

## 验证计划

| 轮次 | 配置 | 验证目标 |
|------|------|---------|
| R0 | 基线 (PIPE_FINE=0) | 锚定基线 |
| R1 | + L5 only | pipe_ring_ I/O 重叠 |
| R2 | + L5 + L1 | CPU cache 增量 |
| R3 | + L5 + L4 | L4 旁路填充跨 query |
| R4 | 全开 | 叠加上限 |

测试矩阵: SIFT1M O_DIRECT/Buffered 1T/4T, DEEP10M O_DIRECT/Buffered 4T/12T

## 进度

- [ ] Step 1: pipe_ring_ 基础设施 (L5)
- [ ] Step 2: 预取提交 (L5)
- [ ] Step 3: L4 旁路填充
- [ ] Step 4: Phase B 对接
- [ ] Step 5: L1/L2/L3 预取
- [ ] R0-R4 验证

## NOTES

- 与 `SPEC_PREFETCH=1` 可共存（不同层：block cache vs vecblocks 页）
- 不改 I/O 粒度（避免重蹈 [[DEC-061]]）
- pipe_ring_ 是 thread_local，多线程安全
- 系统优化不是非此即彼，而是彼此依赖的层叠结构
