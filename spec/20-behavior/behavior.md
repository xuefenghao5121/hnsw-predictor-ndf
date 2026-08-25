# DiskHNSW — Behavior

> scope: product (20-behavior)
> status: stable | perf: not-established | bootstrap: adopt
> Observed Trunk SHA: `d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755`

本文件承载核心可观察行为契约（`{#BEH-*}` draft IDs）。性能相关收益一律
`not-established`，须经 `spec/50-verification/` 协议验证。

## 两阶段搜索 {#BEH-001}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

DiskHNSW MUST 以两阶段执行 KNN 检索：PQ 粗筛（Phase A）生成候选集，精确精排
（Phase B）对候选按真实 L2 距离重排返回 top-K。启用条件由运行时旋钮 `TWO_STAGE`
与 `PQ_CODES_PATH` 控制（[[API-010]]）。

1. `TWO_STAGE=1` 且 PQ 编码已加载时，进入两阶段路径。
2. 否则退回全内存 L0 扫描路径（无 PQ）。

## 贪心下降入口定位 {#BEH-002}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

搜索 MUST 从图入口节点起，在常驻内存的上层（Layer 1+）做贪心下降，定位 Layer 0 的
入口 `new_id`。上层导航 MUST NOT 触发向量 I/O。

## PQ 粗筛 {#BEH-003}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

Phase A MUST 使用常驻内存的 CSR 邻接表遍历 Layer 0，并以 PQ ADC（Asymmetric Distance
Computation）近似距离筛选出候选集。每 query 预计算 PQ 距离表
（`[M * ksub]`，SIMD 化），距离计算退化为查表（[[API-001]]）。

## 精确精排 {#BEH-004}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

Phase B MUST 对 PQ 候选集按 4KB 页粒度读取真实向量并做精确 L2 重排：

1. `flat_vec_cache` 命中时直接取向量，跳过 I/O（[[BEH-008]]）。
2. miss 时经 WILLNEED 预取 + pread 4KB 页读取（[[BEH-007]]）。
3. 结果按精确 L2 排序返回 top-K。

## 块缓存 {#BEH-005}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

BlockCache MUST 按需从磁盘 `blocks.bin` 加载 block 并缓存于内存槽位（默认 64 槽，
约 16MB），采用可插拔替换策略（[[API-004]]），并支持 O_DIRECT / page-cache 清除等
I/O 模式（[[API-002]]）。缓存淘汰 MUST 由策略的 `selectVictim` 决定。

## 图引导预取 {#BEH-006}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

GraphPrefetcher MUST 利用常驻内存的图结构（route 表）预知下一批待访问 block，并批量
提交 io_uring 异步预取，将数据插入 BlockCache（[[API-005]]）。

## WILLNEED 页缓存预取 {#BEH-007}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

页缓存预取 MUST 支持：

1. `L4_WILLNEED`：pread 前 `posix_fadvise(POSIX_FADV_WILLNEED)` 启动内核异步 readahead。
2. `WILLNEED_BG`：无锁 SPSC 后台线程提交 WILLNEED（推荐 8T+）。
3. `PAGE_MERGE_BG`：后台合并连续页减少 syscall（仅 256MB 推荐，512MB 有害）。

> 收益数字 not-established，须 sustained 复测。见 [[CON-SLA-004]]。

## flat_vec_cache 热向量缓存 {#BEH-008}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

BlockCache MUST 维护进程内 `flat_vec_cache`（LRU 热向量槽位，`FLAT_VEC_MB` 控制容量），
Fine Rerank 命中时跳过向量 I/O；精排回填热向量。

## 自适应 EF（PQ gap 启发式） {#BEH-009}
<!-- ndf: kind=req level=should layer=L1 status=stable since=0.1 source=observed -->

`ADAPTIVE_EF=1` 时 SHOULD 依据 PQ 距离间隙启发式动态确定每 query 的候选数，替代固定
`REFINE_EF`。收益须 sustained 口径验证。

## 学习式 EF（GBDT） {#BEH-010}
<!-- ndf: kind=req level=should layer=L1 status=stable since=0.1 source=observed -->

`LEARNED_EF=1` 时 SHOULD 使用 `include/gbdt_model.h` 的 GBDT 多特征模型
（`gbdt_predict`）预测每 query 候选数，乘以 `GBDT_MARGIN` 缩放。模型须与官方
query 池重训练，禁止 self-match。

## VisitedList 访问标记 {#BEH-011}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

搜索 MUST 使用 `VisitedList`（`uint8_t` 标记数组 + `curV` 版本号）避免重复访问节点；
`VL_POOL_THREADS` 控制多线程下的池化阈值（[[API-001]]）。

## ID 映射 {#BEH-012}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

检索 MUST 维护 `old_id`（hnswlib 内部）↔ `new_id`（BFS 重排后）双向映射，搜索结果
以 `old_id`（label）返回。见 [[DEF-001]]。

## 并发搜索 {#BEH-013}
<!-- ndf: kind=req level=should layer=L1 status=stable since=0.1 source=observed -->

`batchSearchConcurrent` 以多线程共享 BlockCache 与 GraphPrefetcher；多线程下 MUST 使用
`FINE_PREAD=1`（io_uring 非线程安全，见 [[CON-004]]）。FineRerank 懒初始化 MUST 用
`std::call_once` 保证线程安全。

## 事件驱动批量搜索 {#BEH-014}
<!-- ndf: kind=req level=may layer=L1 status=stable since=0.1 source=observed -->

`batchSearchEventDriven` MAY 采用单线程多查询状态机，查询 A 阻塞 I/O 时切换到查询 B，
避免锁竞争（[[API-001]]）。

## 召回一致性 {#BEH-015}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

两阶段搜索的召回 MUST 与全内存 HNSW 在相同 ground truth 下可比（目标 ≥95%，draft）。
召回验证协议见 [[VER-006]]。

## 跨架构 SIMD 分发 {#BEH-016}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 source=observed -->

距离计算 MUST 经 `simd.h` 编译期分发到 AVX2 / NEON / 标量实现；同一天量化的索引数据
MUST 可跨 x86 与 ARM 平台复用。见 [[ARCH-006]]、[[API-007]]。

## 分层 Vamana 建图 {#BEH-027}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.2 source=promote model=hierarchical-vamana-build -->

Trunk 默认建图入口 `build_index` MUST 以「HNSW 几何层分配 + 每层 Vamana（GreedySearch +
RobustPrune, α）」构建图结构，替换原整图 hnswlib 建边：

1. 层分配 MUST 按 HNSW 几何分布（`level = floor(-ln(U) * mL)`，`mL = 1/ln(M)`）确定每点最高层。
2. 每层 MUST 以 GreedySearch/beam 生成候选，再经 RobustPrune(α) 剪枝出边，对称化后二遍 prune。
3. 导出的 GraphStructure MUST 与现有 DiskHNSW reorder / blocks / PQ / 搜索壳兼容（[[ARCH-007]]）。
4. 默认运行点 MUST 为 `M=16 R0=32 Rup=16 beam=32 α=1.2 α2=0 rounds=3 seed=42`（[[DEC-003]]）。
5. 搜索路径 / Fine Rerank / BlockCache / PQ 不变；不晋升 GBDT（`LEARNED_EF`）。

> source: poc/hierarchical-vamana/ndf/TOPIC.md ; spec/open/proposal-promote-hierarchical-vamana.md @ d0ae5dd
> track: promote ; Topic: hierarchical-vamana
