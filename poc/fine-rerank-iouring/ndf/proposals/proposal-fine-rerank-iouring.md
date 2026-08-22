# Proposal: Per-Thread io_uring 替代 WILLNEED_BG + pread 的 Fine Rerank I/O 路径

> track: poc
> 日期: 2026-08-06
> Status: draft (待开题审核)
> 关联: [[BEH-024]]、[[BEH-027]]、[[BEH-028]]、[[API-012]]、[[API-013]]、[[CON-SLA-014]]、[[CON-SLA-016]]、[[CON-SLA-018]]、[[DEC-068]]、[[DEC-070]]、[[DEC-074]]、[[DEC-075]]、[[REF-HELMSMAN]]

## 1. 背景与动机

### 1.1 当前 Fine Rerank I/O 路径

当前主线 (`FINE_PREAD=1` + `L4_WILLNEED=1` + `WILLNEED_BG=1`):

```
Phase A (PQ 粗筛, 纯内存) -> 产出 cand_ids
  ↓
Phase B (Fine Rerank):
  1. 收集 pages_needed (查 vec_route_table_)
  2. 搜索线程: 设置 BG slot ready flag (atomic store)
  3. BG 线程: yield 轮询 -> 检测 flag -> 逐页 posix_fadvise(WILLNEED)
  4. 内核: 启动 readahead (异步)
  5. 搜索线程: pread 逐页读 (固定顺序, 阻塞等待 readahead 完成)
```

### 1.2 问题分析

**R5c mincore 诊断 (256MB cgroup) 揭示的事实:**

- vecblocks 总页数: 126,993
- page cache 中: 15,355 (12.1%)
- **不在 page cache: 111,638 (87.9%)**

每次查询:
- 候选 ~100 个, FVC 命中 ~46 (45.7%), 需 I/O ~54
- 其中 page cache 命中 ~6 (12%), **需磁盘读取 ~48 页**
- 实测 pgmajfault: 5,114 / 200 queries = **~25 页/query 真实磁盘 I/O**

**87.9% 的页不在 page cache 中, 这些页必须走磁盘 I/O。磁盘 I/O 路径的效率直接决定查询性能。**

### 1.3 当前路径的三个效率问题

#### 问题 1: BG 线程轮询延迟

```
搜索线程: 设 ready flag -> 立即开始 pread
BG 线程:  yield -> 检测 flag -> 逐页 fadvise (N 次 syscall)
```

搜索线程和 BG 线程之间存在时间差。BG 线程用 `std::this_thread::yield()` 轮询,
16T 并发时需处理 16 个 slot × ~100 页 = 1600 次 fadvise。搜索线程可能在 BG 线程
完成 fadvise 之前就开始 pread, 导致部分页未被 hint, pread 阻塞。

#### 问题 2: pread 固定顺序阻塞

```cpp
for (uint32_t pg : pages_needed) {
    pread(fd, buf, 4096, pg << 12);  // 阻塞直到此页就绪
}
```

即使内核已 readahead 完成第 10 页, pread 仍在等第 1 页。25 页中如果第 1 页最慢,
后面 24 页都得等。无法按完成顺序处理。

#### 问题 3: syscall 数量

每页 1 次 fadvise + 1 次 pread = 2N 次 syscall。25 页 = 50 次 syscall/query。
16T 并发 = 800 次 syscall/批。

### 1.4 提议的替代路径

**Per-thread io_uring (buffered 模式)** 替代 WILLNEED_BG + pread:

```
Phase B (Fine Rerank):
  1. 收集 pages_needed
  2. 搜索线程: 1 次 io_uring_submit 批量提交所有页
  3. 内核: 立即并行启动所有读
  4. 搜索线程: 按完成顺序处理 (CQE 通知, 先到先处理)
```

### 1.5 关键设计决策: buffered 模式 (非 O_DIRECT)

使用 io_uring buffered read (非 O_DIRECT):
- 页照样进 kernel page cache -> **跨 query 复用不受影响**
- 不绕过 page cache -> 不丢失 12.1% 的热页命中
- 与当前 WILLNEED+pread 的 page cache 行为一致

### 1.6 与 io-pipelining POC 的区别

io-pipelining (rejected, DEC-071) 探索的是在 WILLNEED 之上叠加 pipe_ring_ 预取层。
本提案探索的是**替换整个 I/O 路径** -- 用 io_uring 替代 WILLNEED_BG + pread,
不是叠加, 是替代。

## 2. 预期收益

| 指标 | WILLNEED_BG + pread (当前) | per-thread io_uring (预期) |
|------|---------------------------|---------------------------|
| 提交延迟 | BG yield 轮询 + N×fadvise | 1×io_uring_submit |
| 内核启动读 | 延迟 (BG 处理后) | 立即 |
| 处理顺序 | 固定 (pread 顺序, 阻塞) | 完成顺序 (CQE, 先到先处理) |
| syscall/query | 2N (~50) | 1 |
| page cache 复用 | ✅ | ✅ (buffered 模式) |
| 线程安全 | ✅ (pread 天然安全) | ✅ (per-thread ring, 无共享) |
| BG 线程依赖 | 需要 (SPSC slot + yield 轮询) | 不需要 |
| 内存开销 | BG 线程栈 + page cache | per-thread ring (256 entries × 8KB ≈ 2MB/thread) |

### 预期 QPS 提升

- **1T 256MB**: +5-15% (消除 BG 轮询延迟 + 完成顺序处理)
- **16T 256MB**: +10-20% (消除 1600 次 fadvise syscall 压力 + 并行完成)
- **1T 512MB**: +0-5% (page cache 充裕, I/O 占比低, 收益有限)
- **DEEP10M**: 不确定 (I/O 仅占 7%, 但 majfault=68K, 可能减少 syscall 开销)

## 3. 实现方案

### 3.1 Per-thread io_uring 实例

```cpp
// 每个搜索线程一个独立 IoUring 实例
class FineRerankIO {
    IoUring ring_;          // 256 entries, 8KB buffers
    int vec_blocks_fd_;
    // ...
public:
    // 批量提交所有页, 1 次 syscall
    void submitAll(const std::set<uint32_t>& pages);
    
    // 按完成顺序获取就绪页 (非阻塞)
    bool tryGetPage(uint32_t& page, const char*& data);
    
    // 等待所有页完成
    void waitAll();
};
```

### 3.2 Fine Rerank 改造

```cpp
// 旧路径 (WILLNEED_BG + pread):
// 1. submit to BG slot
// 2. for each page: pread (blocking, fixed order)

// 新路径 (per-thread io_uring):
FineRerankIO io;  // thread_local
io.submitAll(pages_needed);  // 1 syscall

// 按完成顺序处理 (先到先算距离)
while (io.hasPending()) {
    uint32_t pg;
    const char* data;
    if (io.tryGetPage(pg, data)) {
        // 处理此页上的候选向量
        for (candidate c : candidates_on_page[pg]) {
            consider(c.nid, reinterpret_cast<const float*>(data + c.oip));
        }
    }
}
```

### 3.3 环境变量

- `FINE_IOURING=1`: 启用 per-thread io_uring 路径 (opt-in, 默认关闭)
- 与 `FINE_PREAD` 互斥 (两者不能同时启用)
- 与 `L4_WILLNEED` / `WILLNEED_BG` 互斥 (io_uring 替代两者)

### 3.4 POC 代码位置

所有代码在 `poc/fine-rerank-iouring/`:
- `disk_hnsw_iouring.cpp`: patched copy
- `disk_hnsw_iouring.h`: patched header
- `benchmark_iouring.cpp`: benchmark
- `Makefile`: 独立构建
- `run_bench.sh`: R0-Rn 脚本

**MUST NOT 改 Trunk `src/`** (BEH-018)

## 4. 验证协议

### 4.1 基线

当前 Trunk (commit `476b953`):
- SIFT1M 256MB 1T: 2,830 QPS / 95.80% recall
- SIFT1M 256MB 16T+BG+POOL: 18,675 QPS / 95.80% recall
- SIFT1M 512MB 1T: 3,366 QPS / 95.75% recall
- SIFT1M 512MB 16T+BG+POOL: 30,332 QPS / 95.75% recall

### 4.2 实验轮次

| 轮次 | 配置 | 目标 |
|------|------|------|
| R0 | 基线 (WILLNEED_BG + pread) | 确认基线 |
| R1 | per-thread io_uring (buffered) | 核心对比 |
| R2 | io_uring + page merge (合并连续页) | 减少 syscall |
| R3 | io_uring + 完成顺序处理 | 验证乱序处理收益 |
| R4 | 16T 并发 | 多线程扩展性 |
| R5 | DEEP10M 2GB | 大数据集验证 |

### 4.3 SLA 合规

[[CON-SLA-014]] (512MB) + [[CON-SLA-016]] (256MB) + [[CON-SLA-018]] (256MB 16T):
- Recall ≥95%
- oom = 0
- peak ≤ cgroup limit

### 4.4 晋升条件

- 256MB 16T QPS 提升 >5%: 候选 promote
- 512MB 无回归: 必须
- Recall 不变: 必须
- 线程安全 (16T 稳定): 必须

## 5. 风险与缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| io_uring 多线程不稳定 | 中 | per-thread 实例, 无共享状态; FineRerank race fix 已验证 |
| 内存开销 (2MB/thread) | 低 | 16T = 32MB, 256MB cgroup 下可接受 |
| page cache 行为变化 | 低 | buffered 模式, 与 pread 行为一致 |
| 收益不如预期 | 中 | R1 先验证 1T, 不行则关闭 |
| io_uring 内核版本依赖 | 低 | Linux 5.1+ 支持, 当前 7.0.0 内核充足 |

## 6. 不做的事

- 不用 O_DIRECT (保留 page cache 复用)
- 不改 Phase A (PQ 粗筛路径不变)
- 不改 Trunk `src/` (POC 代码在 `poc/` 下)
- 不叠加 WILLNEED (io_uring 完全替代)
- 不改 flat_vec_cache (FVC 仍然在前, io_uring 处理 FVC miss 的候选)

## 7. 与现有条款的关系

| 条款 | 关系 |
|------|------|
| [[BEH-024]] | L4 管理已关闭, 本 POC 是 L4 之后的下一优化方向 |
| [[BEH-027]] | WILLNEED_BG 行为, 本 POC 提议替代 (不删除, opt-in 切换) |
| [[BEH-028]] | PAGE_MERGE_BG, io_uring 路径中用 io_uring 合并替代 |
| [[API-012]] | L4_WILLNEED, 本 POC 新增 FINE_IOURING |
| [[CON-SLA-014/016/018]] | 验证 SLA, 不改 SLA |
| [[DEC-070]] | WILLNEED promote, 本 POC 提供替代路径 (WILLNEED 保留 fallback) |
| [[DEC-074]] | WILLNEED_BG promote, 本 POC 可能替代 |
| [[REF-HELMSMAN]] | HELMSMAN 的 SPDK 思路启发 (io_uring 是内核态替代) |
| io-pipelining (rejected) | 不同: io-pipelining 叠加 pipe_ring_, 本 POC 替换整个路径 |

## 8. 草稿条款

| ID | 类型 | 描述 |
|----|------|------|
| BEH-029 (draft) | behavior | Fine Rerank io_uring 路径行为 |
| API-014 (draft) | interface | FINE_IOURING 环境变量 |
| DEC-076 (draft) | decision | per-thread io_uring vs WILLNEED_BG 决策 |
