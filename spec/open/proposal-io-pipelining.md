# Proposal: I/O Pipelining - 统一多层预取架构

> track: poc
> 关联: [[DEC-060]] 方向 2、[[DEC-062]]、[[BEH-001]]、[[BEH-007]]、[[CHR-006]]、[[CON-SLA-011]]、[[CON-POC-001]]
> 日期: 2026-08-01
> Status: **Active (draft)** — SIFT1M 负结果 + DEEP10M 相对证据见 [[DEC-063]]；
> post-memopt pipe 无收益见 [[DEC-064]]；BEH-021…023 / CON-SLA-013 保持 draft；未 promote pipe
> 修订: 2026-08-01 r2/r3；2026-08-02 同步 DEC-063/064 卫生

## 1. 问题陈述

当前 `searchKnn()` 的两阶段流程完全串行：

```
Phase A: searchLayer0() (PQ ADC, CPU 密集, 无向量 I/O)
    -> 返回 coarse 候选集
Phase B: Fine Rerank (收集候选 -> 检查 cache -> 批量 io_uring 4KB 读 -> 等待完成 -> 算 L2)
```

Phase A 期间 NVMe I/O 带宽完全空闲；Phase B 期间 CPU 等待 I/O 完成后才算距离。
两个阶段无重叠。

**实测延迟分解（SIFT1M, 512MB cgroup, O_DIRECT, 1T, REFINE_EF=100）**：

| 阶段 | 耗时 | 说明 |
|------|------|------|
| Phase A (PQ 粗筛) | ~500μs | CPU 密集 (PQ 查表 + 图遍历) |
| Phase B I/O 等待 | ~7000μs | ~100×4KB 随机读, NVMe ~70μs/读 (io_uring 并行) |
| Phase B 计算距离 | ~100μs | 100 次 L2 SIMD |
| **总计** | **~7600μs** | QPS ≈ 130 |

Phase A 的 500μs 完全可以用来提前提交 I/O，隐藏部分 I/O 延迟。

## 2. 统一多层预取架构

### 2.1 设计原则

系统优化不是非此即彼，而是彼此依赖的层叠结构。所有预取层协作，不分模式分治：

```
Disk (NVMe, ~50-70μs/page)
    ↓ io_uring read (O_DIRECT or Buffered)
L5: pipe_ring_ 应用缓冲 (~800KB, 单 query 生命周期)
    ↓ 数据已在内存中
L4: Page Cache (cgroup_limit - RSS, ~240-390MB, 跨 query 持久化)
    ↑ Buffered 模式下 pipe_ring_ 读取自然填充此层
    ↑ 可主动 readahead() 预填充
    ↓ pread 命中
L1/L2/L3: CPU Cache (~30MB L3, 单次计算生命周期)
    ↑ _mm_prefetch 向量数据 (8 cache lines / 128 floats)
    ↓ 命中后算 L2 距离 (~4ns vs ~40ns)
```

### 2.2 各层职责

#### L5: pipe_ring_ 应用缓冲（两种模式都保留）

| 属性 | 说明 |
|------|------|
| 容量 | ~800KB (200×4KB, 可调) |
| 生命周期 | 单 query，Phase B 结束后释放 |
| 机制 | 独立 io_uring 实例，thread_local |
| O_DIRECT 读取 | 数据 -> app buffer (L5 only) |
| Buffered 读取 | 数据 -> app buffer (L5) **+ page cache (L4)** |

**Buffered 模式下 pipe_ring_ 读取的双重效果**：
- 当前 query：从 L5 buffer 直接取数据算距离（零拷贝）
- 未来 query：同样的页若仍在 L4 中，Phase B 的 pread 直接命中

pipe_ring_ 是 Phase A 期间 I/O 与 CPU 并行的**唯一主动机制**，两种模式都必须保留。
Buffered 模式下 page cache 预算虽有限，但 pipe_ring_ 确保当前 query 的 I/O 不被
page cache 容量和 LRU 策略制约。

#### L4: Page Cache 跨 query 抽象缓存

| 属性 | 说明 |
|------|------|
| 容量 | `cgroup_limit - RSS`（SIFT1M ~240MB, DEEP10M ~390MB） |
| 生命周期 | 跨 query 持久，OS LRU 管理 |
| 填充方式 | Buffered I/O 自然填充 / 主动 `readahead()` |
| 命中延迟 | ~1-2μs/page（vs NVMe ~70μs/page） |
| 限制 | 预算有限，与 RSS 竞争 cgroup；大规模下覆盖率趋零 |

**L4 的价值不在单 query，在于跨 query 局部性**：
- 同一区域反复搜索时，L4 命中率上升
- pipe_ring_ 的 Buffered 读取每次都为 L4 填充
- L4 满时 OS 自动 LRU 驱逐冷页
- 规模增大时 L4 覆盖率趋零（SIFT1M ~48%, DEEP10M ~10%, 100M ~4%），但非零即有价值

**O_DIRECT 模式下 L4 的角色**：
- 当前 query 的 pipe_ring_ O_DIRECT 读**不填充** L4
- 可选：用 `readahead()` 旁路填充 L4（为未来 query 预热），代价是一次额外的 buffered I/O
- 是否值得取决于跨 query 局部性强度，作为 POC 可选项验证

#### L1/L2/L3: CPU Cache 计算加速

| 属性 | 说明 |
|------|------|
| 容量 | L1 ~32KB, L2 ~256KB, L3 ~30MB |
| 生命周期 | 单次距离计算 |
| 机制 | `_mm_prefetch` / `__builtin_prefetch` |
| 粒度 | 64B cache line（SIFT 128 floats = 512B = 8 lines; DEEP 96 floats = 384B = 6 lines） |
| 延迟收益 | L1 ~4ns vs L3 miss ~40-70ns |

数据无论来自 L5 还是 L4，距离计算前都可以 `_mm_prefetch`。
Phase B 遍历候选时，预取下一个候选的向量到 L1，隐藏内存访问延迟。

### 2.3 统一管线流程

```
Phase A (searchLayer0 核心循环):
  候选加入 top_candidates (rank ≤ PIPE_THRESHOLD)
    -> [L5] pipe_ring_->submitRead(page0)
       ├─ O_DIRECT: 数据 -> app buffer (L5)
       └─ Buffered:  数据 -> app buffer (L5) + page cache (L4)  ← 双重效果
    -> [L4] (可选, Buffered 模式) readahead(fd, page, 4096)
            // pipe_ring_ buffer 满时仍可旁路填充 L4
  Phase A 继续 CPU 工作 (PQ 查表 + 图遍历)

Phase B (Fine Rerank):
  1. reap pipe_ring_ completions -> L5 buffer 就绪
  2. 遍历候选:
     a. flat_vec_cache hit -> 直接算
     b. L5 hit (pipe_ring_) -> _mm_prefetch 向量 -> 算距离
     c. L4 hit (page cache, Buffered 模式) -> pread 命中 -> _mm_prefetch -> 算距离
     d. miss -> vec_ring_ 同步 I/O -> 算距离
  3. 每个 consider() 前预取下一个候选的向量到 L1/L2/L3
```

### 2.4 实现要点

#### 2.4.1 pipe_ring_ 基础设施

- 在 `disk_hnsw.cpp` 中新增 `thread_local IoUring pipe_ring_`（独立于 `vec_ring_`）
- buffer pool: ~200 个 4KB 对齐 slot（`posix_memalign` 4096 对齐）
- 初始化时机：`buildFineRerank()` 成功后
- O_DIRECT 模式：`pipe_ring_` 以 `O_DIRECT` 打开 fd 或使用 `IO_FIXED_BUFFER`
- Buffered 模式：`pipe_ring_` 以 buffered I/O 提交，自然填充 L4

#### 2.4.2 预取触发与节流

在 `searchLayer0()` 核心循环中，候选加入 `top_candidates` 后：

```cpp
if (kPipeFine && fine_rerank_ok_) {
    uint32_t b = vec_route_table_[neighbor_id];
    uint64_t off = 4096ull + (uint64_t)b * vec_block_size_
                 + block_data_offset_[b]
                 + (uint64_t)node_slot_table_[neighbor_id] * dim_ * sizeof(float);
    uint32_t page0 = (uint32_t)(off >> 12);
    if (piped_pages_.find(page0) == piped_pages_.end()) {
        int buf_idx = pipe_ring_->allocBuffer();
        if (buf_idx >= 0) {
            pipe_ring_->submitReadNF(vec_blocks_fd_, (off_t)page0 << 12, 4096, buf_idx, page0);
            piped_pages_.insert(page0);
            // cross-page: 还需提交 page0+1
            if (cross) {
                int buf2 = pipe_ring_->allocBuffer();
                if (buf2 >= 0) {
                    pipe_ring_->submitReadNF(vec_blocks_fd_, (off_t)(page0+1) << 12, 4096, buf2, page0+1);
                    piped_pages_.insert(page0 + 1);
                }
            }
        }
    }
}
```

**节流策略**：
- 仅预取 rank ≤ `PIPE_THRESHOLD` 的候选（有望进入 Phase B 的候选）
- 去重：`unordered_set<uint32_t> piped_pages_` 防止同页重复提交
- pipe_ring_ buffer 满时停止提交（不阻塞 Phase A）

#### 2.4.3 L4 旁路填充（可选）

```cpp
// Buffered 模式下, pipe_ring_ buffer 满时仍可为 L4 预热
if (kPipeFine && !kFineDirect && piped_pages_.size() >= pipe_ring_capacity) {
    readahead(vec_blocks_fd_, (off_t)page0 << 12, 4096);  // 旁路填充 L4
}
```

- 仅 Buffered 模式可用（O_DIRECT 的 readahead 无意义）
- 代价：一次 syscall，但 kernel 异步执行不阻塞
- 收益：L4 预热，未来 query 可能命中

#### 2.4.4 Phase B 对接

```cpp
// Phase B 开始:
// 1. flush + reap pipe_ring_ 已就绪页
pipe_ring_->flushSqe();
pipe_ring_->submit();
std::unordered_map<uint32_t, const char*> pipe_page_buf;
// reap 非阻塞完成的页 (不带 waitCompletion)
reapNonBlocking(pipe_ring_, pipe_page_buf);

// 2. 遍历候选, 按层级访问
for (const auto& c : io_cands) {
    const char* vec;
    // L5: pipe_ring_ buffer
    if (auto it = pipe_page_buf.find(c.page0); it != pipe_page_buf.end()) {
        vec = resolveVec(it->second, c);  // 处理跨页拼接
    }
    // L4: page cache (Buffered 模式, pread 命中)
    else if (!kFineDirect && tryPreadFromPageCache(c, vec)) {
        // pread 命中 page cache
    }
    // Miss: vec_ring_ 同步 I/O
    else {
        // 走原有 vec_ring_ 路径
        continue;
    }
    
    // L1/L2/L3: 预取下一个候选的向量
    if (next_idx < io_cands.size()) {
        prefetchVecToL1(getVecPtr(io_cands[next_idx]));
    }
    consider(c.nid, vec);
}
```

#### 2.4.5 L1/L2/L3 预取

```cpp
inline void prefetchVecToL1(const char* vec_ptr) {
    // SIFT: 128 floats = 512B = 8 cache lines
    // DEEP: 96 floats = 384B = 6 cache lines
    constexpr int vec_bytes = /* dim * sizeof(float) */;
    constexpr int cache_lines = (vec_bytes + 63) / 64;
    for (int i = 0; i < cache_lines; i++) {
        _mm_prefetch(vec_ptr + i * 64, _MM_HINT_T0);
    }
}
```

- 每次 `consider()` 前预取下一个候选的向量
- 开销：6-8 条 `_mm_prefetch`（~6-8ns）
- 收益：消除 L2 miss stall

### 2.5 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `PIPE_FINE=1` | 0 (关) | 开启 I/O Pipelining (L5 pipe_ring_) |
| `PIPE_THRESHOLD` | REFINE_EF | 预取触发阈值：仅预取 rank ≤ 此值的候选 |
| `PIPE_L4=1` | 0 (关) | 开启 L4 旁路填充（Buffered 模式下 readahead 预热 page cache） |
| `PIPE_L1=1` | 0 (关) | 开启 L1/L2/L3 向量预取（_mm_prefetch） |

三个开关独立控制，可组合验证各层独立贡献和叠加效果。

### 2.6 预期收益分析

#### 各层独立贡献估算

| 层 | 模式 | 机制 | 预期收益 | 说明 |
|----|------|------|----------|------|
| L5 | O_DIRECT | pipe_ring_ I/O 重叠 | SIFT1M +7%, DEEP10M +33-48% | 隐藏 Phase A 期间的 I/O |
| L5 | Buffered | pipe_ring_ I/O 重叠 | SIFT1M +3-5% | page cache 命中时 I/O 已很快，重叠收益小 |
| L4 | Buffered | readahead 旁路 + 跨 query | 跨 query 累积 | 难以单 query 量化，取决于工作负载局部性 |
| L1 | 两种 | _mm_prefetch 向量 | ~4-7μs/query | 100 候选 × 40-70ns L3 miss，占总延迟 <0.1% |

#### 叠加效果（O_DIRECT, SIFT1M 1T）

| 配置 | QPS 预估 | vs 基线 |
|------|---------|---------|
| 基线 (PIPE_FINE=0) | 130 | - |
| + L5 only | ~140 | +7% |
| + L5 + L1 | ~141 | +7.7% |
| (L4 不适用 O_DIRECT) | - | - |

#### 叠加效果（Buffered, SIFT1M 1T）

| 配置 | QPS 预估 | vs 基线 |
|------|---------|---------|
| 基线 (PIPE_FINE=0) | 2450 | - |
| + L5 only | ~2530 | +3.3% |
| + L5 + L4 | ~2550 | +4.1% (含跨 query 累积) |
| + L5 + L4 + L1 | ~2560 | +4.5% |

#### 叠加效果（O_DIRECT, DEEP10M 4T）

| 配置 | QPS 预估 | vs 基线 |
|------|---------|---------|
| 基线 (PIPE_FINE=0) | 169 | - |
| + L5 only | ~220-250 | +30-48% |
| + L5 + L1 | ~225-255 | +33-51% |

> ⚠️ 以上为理论估算。DEEP10M 收益最大因为 Phase A (~7ms) 远长于 SIFT1M (~0.5ms)，
> I/O 有充足时间在 Phase A 期间完成。

### 2.7 风险与约束

1. **预取浪费**：Phase A 候选集动态变化，被淘汰候选的预取 I/O 浪费带宽。
   缓解：节流策略仅预取 rank ≤ PIPE_THRESHOLD 的候选

2. **io_uring 队列深度**：pipe_ring_ SQE + Phase B vec_ring_ SQE 总数可能超 NVMe 队列深度。
   缓解：pipe_ring_ 大小限制为 PIPE_THRESHOLD，Phase B 开始前 drain pipe_ring_

3. **内存开销**：
   - pipe_ring_ buffer pool: ~200×4KB = 800KB (thread_local)
   - piped_pages_ set: ~200×4B = 800B (thread_local)
   - 总计 <1MB/thread，可接受

4. **线程安全**：pipe_ring_ 是 thread_local（与 vec_ring_ 一致），多线程安全

5. **与 [[DEC-061]] 的关系**：Read Coalescing 试图减少 I/O 次数（已证明无效）；
   本提案不改 I/O 次数或粒度，而是让 I/O 与 CPU 并行 + 多层缓存协作。
   不共享 DEC-061 的「合并随机读」假设

6. **L4 跨 query 局部性假设**：L4 收益依赖工作负载的访问局部性。
   若 query 均匀随机分布，L4 命中率低。POC 需测量实际 L4 hit rate

### 2.8 POC 验证计划

在 `poc/io-pipelining/` 中实现，分层验证各层独立贡献和叠加效果。

**主目标 = Buffered**（[[DEC-062]]）；O_DIRECT 为辅。**v1 smoke 不可信，禁止引用。**

| 轮次 | 配置 | 验证目标 |
|------|------|---------|
| R0 | 基线 (PIPE_FINE=0) | 诚实 cgroup 下锚定；对齐 §7 / NOTES |
| R1 | + L5 only (PIPE_FINE=1) | pipe_ring_ / 主动填 L4 |
| R2 | + L5 + L1 | CPU cache 增量 |
| R3 | + L5 + L4 | L4 旁路跨 query |
| R4 | 全开 | 叠加上限 |

测试矩阵（顺序：Buffered 先于 O_DIRECT）：
- SIFT1M **Buffered** 1T/4T（主）
- SIFT1M O_DIRECT 1T/4T（辅）
- DEEP10M Buffered / O_DIRECT 按需

§7 基线纪律见 `proposal-goal-clarification` / NOTES：偏差 >10% vs [[CHR-006]]/[[CON-SLA-011]] 先查根因。

## 3. 拟新增/修订条款

### {#BEH-021} (draft, 修订)

> track: poc | status: draft | level: tbd

当 `PIPE_FINE=1` 时，`searchLayer0()` 在候选加入 `top_candidates` 时异步提交对应
4KB vecblocks 页的 io_uring 读取到独立 pipeline ring（`pipe_ring_`）。两种 I/O 模式
（O_DIRECT / Buffered）均启用。

**L1 草案契约**：
1. 预取触发：邻居节点加入 `top_candidates` 且 rank ≤ `PIPE_THRESHOLD` 时提交
2. 去重：同一页不重复提交
3. 独立 io_uring 实例：`pipe_ring_` 与 `vec_ring_` 分离
4. Phase B 对接：先 reap `pipe_ring_` 已就绪页（L5），再查 page cache（L4），最后 vec_ring_
5. `PIPE_FINE=0`（默认）时 MUST 零开销，行为与基线完全一致
6. 跨页向量：cross-page 候选需提交 page0 和 page0+1 两个 SQE
7. Buffered 模式下 pipe_ring_ 读取自然填充 L4 (page cache)，提供跨 query 缓存

### {#BEH-022} (draft, 新增)

> track: poc | status: draft | level: tbd

当 `PIPE_L1=1` 时，Phase B 遍历候选前 MUST 对下一个候选的向量地址执行 `_mm_prefetch`，
将其预取到 L1/L2/L3 CPU cache。预取粒度 = `ceil(dim * sizeof(float) / 64)` 条 cache line。

### {#BEH-023} (draft, 新增)

> track: poc | status: draft | level: tbd

当 `PIPE_L4=1` 且 Buffered 模式时，pipe_ring_ buffer 满后仍可通过 `readahead()` 旁路
填充 L4 (page cache)，为后续 query 预热。O_DIRECT 模式下此开关无效。

### {#API-010} (draft, 修订)

> track: poc | status: draft | level: tbd

| 环境变量 | 类型 | 默认值 | 取值范围 | 说明 | 关联条款 |
|----------|------|--------|---------|------|----------|
| `PIPE_FINE` | int | 0 | 0/1 | 1=Phase A 期间异步预取 Fine Rerank 候选页 (L5) | [[BEH-021]] [[DEC-060]] |
| `PIPE_THRESHOLD` | int | REFINE_EF | `[k, REFINE_EF]` | 预取触发的最大 rank | [[BEH-021]] |
| `PIPE_L1` | int | 0 | 0/1 | 1=开启 L1/L2/L3 CPU cache 向量预取 | [[BEH-022]] |
| `PIPE_L4` | int | 0 | 0/1 | 1=开启 L4 page cache 旁路填充 (仅 Buffered) | [[BEH-023]] |

### {#CON-SLA-013} (draft, 修订 r3)

> track: poc | status: draft | level: tbd | depends-on: [[DEC-062]]

POC 阶段不纳入生产 SLA。**主表 Buffered；辅表 O_DIRECT。** 固定目录正文为准。

主表目标：相对诚实 Buffered R0 有可测增益，方向逼近 hnswlib；辅表保留 130→140 等地板目标。
若负结果，走 [[BEH-020]]。

## 4. 不做的事

- 不改 I/O 粒度（不做 coalescing，避免重蹈 [[DEC-061]]）
- 不改 Phase A 的搜索算法（仅插入预取提交，不改变候选集质量）
- 不改 Phase B 的距离计算逻辑（仅改变 I/O 等待时机和缓存层级）
- 不预取所有候选（节流，仅预取有望进入 Phase B 的候选）
- 不把 POC 数字写入 stable must SLA（[[CON-POC-001]]）
- 不按模式分治（统一管线，各层协作，pipe_ring_ 两种模式都保留）
