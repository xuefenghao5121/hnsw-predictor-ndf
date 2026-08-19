# MODEL: Fine rerank WILLNEED readahead（语义核）

> role: L3-reference（金标 / 行为预言机）  
> 由 [[BEH-024]] 经 `model=` 引用；证据与决策见 [[DEC-070]]；测法仍由 VER / [[CON-SLA-014]]  
> **不是** poc 切片、不是 git patch 账本（[[ARCH-008]]）

## WILLNEED readahead 参考模型 {#MODEL-WILLNEED-001}
<!-- ndf: kind=def level=must layer=L3 status=stable since=0.9 source=deduced -->
<!-- ndf: depends-on=DEC-070,API-012 -->

本模型定义 opt-in WILLNEED 的**可重复行为语义**（与 Trunk 实现应对齐；由 [[BEH-024]] 经 `model=` 引用。实现细节以 `src/` 为准，语义争议以本条为预言机）。

### 启用

同时满足时模型生效：

1. 环境变量 `L4_WILLNEED` 非 0（见 [[API-012]]）
2. Buffered I/O 路径（非仅 O_DIRECT 语义下的「无 page cache 预热」场景；与契约一致时仅 Buffered 发 hint）

默认关闭（`L4_WILLNEED=0`）时，本模型为 no-op。

### 时机

在 Fine rerank 路径中，集合 `pages_needed`（本 query 待读的 vecblocks 页号）**已最终确定之后**，
且在对该集合执行 `pread` / `io_uring` 提交**之前**。

### 操作

对 `pages_needed` 中每一页 `pg`：

```text
posix_fadvise(vec_blocks_fd, (off_t)pg << 12, 4096, POSIX_FADV_WILLNEED)
```

即：按 4KiB 页对齐，向内核发出 WILLNEED 提示，启动异步 readahead。

随后 MUST 继续既有 pread / io_uring 读路径（本模型不替换读路径）。

### 不变量

1. **不减少**磁盘 I/O 量语义：hint 改变时序（串行等待 → 与后续 CPU/pread 重叠），不删除必读页。
2. **无**额外用户态预取环形缓冲要求（对比已废弃的 pipe_ring_ 路径）。
3. 未启用时 MUST NOT 发出上述 WILLNEED 循环。
4. 本模型不规定 QPS/SLA 数字；性能证据属 [[DEC-070]] / 场景 6，不属金标正文。

> rationale: 从已晋升的 l4-cache-mgmt R5 / DEC-070 蒸馏；契约在 [[BEH-024]]，预言机在此，
> 时间轴在 git，探索史在装订器——三者分离。
