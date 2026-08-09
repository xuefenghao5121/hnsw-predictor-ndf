# Proposal: Promote — hybrid pause+yield (BEH-027 amend)

> track: promote
> Status: Implemented on 2026-08-09
> 日期: 2026-08-09
> Promotes: bg-thread-futex (partial)
> 关联: BEH-027 (WILLNEED 后台线程化), DEC-074 (A2 lockless bg 决策)

## 语义核决策

**不要** L3 语义模型。理由：本次变更是对 BEH-027 中 bg_thread 轮询策略的微调（sched_yield → pause+yield），不改变行为语义（fadvise 提交时机、slot 通信协议、page 合并逻辑均不变）。L1+DEC 足够覆盖。

## 背景

POC `bg-thread-futex` R0 系统性评估了 4 种 bg_thread 调度策略：

| 方案 | 1T steady | 16T steady | 结论 |
|------|----------|-----------|------|
| sched_yield (Trunk) | 1,553 | 3,802 | baseline |
| D: futex | -4.6% | +2.5% | 1T 证伪 (wake 延迟→cold pread) |
| E: io_uring | -11.2% | -22.3% | 全面证伪 (async queue delay + SQ race) |
| **B: hybrid pause+yield** | **+4.8%** | **+5.1%** | **全场景帕累托改进 ✅** |

根因分析详见 evidence 文件。

## 变更内容

### BEH-027 amend（L1 行为条款微调）

在 BEH-027 的后台线程轮询描述中，增加 `_mm_pause` 节流策略：

**新增段落**（插入到 BEH-027 现有轮询描述之后）：

> 后台线程在每轮 slot 扫描完成后，MUST 先执行 8 次 `_mm_pause`（~100ns CPU 自旋提示），
> 再调用 `sched_yield()` 让出 CPU。
>
> 该节流策略减少了 sched_yield 频率（降低内核调度开销），同时保持 bg_thread
> 的快速响应能力（pause 期间 CPU 流水线停顿，不消耗执行资源）。
>
> rationale: Profiling 显示纯 sched_yield 在 1T 下消耗 ~18.4% P-core CPU（2,116 次/query）。
> 加入 8x _mm_pause 后全场景正向收益 +0.2%~5.1% steady QPS，无退化。

### DEC-093（产品决策记录）

新增 DEC-093 记录 bg_thread 调度策略选型结论。

## 合入代码

### 代码变更（src/core/disk_hnsw.cpp）

1. `#include <emmintrin.h>` 添加到 include 区
2. bg_thread 循环中 `std::this_thread::yield()` 前插入 8x `_mm_pause()`

**代码 diff（2 行新增 + 1 行修改）**：

```cpp
 // include 区
+#include <emmintrin.h>  // _mm_pause for bg_thread yield throttling

 // bg_thread 循环末尾（~line 1850）
+                            // Hybrid: 8x _mm_pause (~100ns) then yield
+                            _mm_pause(); _mm_pause(); _mm_pause(); _mm_pause();
+                            _mm_pause(); _mm_pause(); _mm_pause(); _mm_pause();
                             std::this_thread::yield();
```

## 验证证据

| 配置 | sched_yield (旧) | hybrid pause+yield (新) | delta |
|------|-----------------|------------------------|-------|
| 1T steady | 1,553 | **1,627** | **+4.8%** |
| 8T steady | 4,079 | 4,089 | +0.2% |
| 16T steady | 3,802 | **3,995** | **+5.1%** |
| recall | 95.52% | 95.52% | 不变 |

测试协议: SIFT1M M=16 EF=65, 256MB cgroup, 15 rounds × 1000 queries, seed 42

> source: poc/bg-thread-futex/ndf/evidence/r0-scaling-sweep-20260809.md

## baseline invalidation

本次变更修改 `src/core/disk_hnsw.cpp`（bg_thread 轮询路径），影响：
- 所有使用 `WILLNEED_BG=1` 的活跃 topic（无活跃 exploring topic，不影响）
- Trunk SHA 合入后更新

## 条款清单

| ID | 操作 | 说明 |
|----|------|------|
| BEH-027 | amend (微调) | 增加 pause+yield 节流策略描述 |
| DEC-093 | new | bg_thread 调度策略选型决策（futex/io_uring 证伪，pause+yield 采纳）|
