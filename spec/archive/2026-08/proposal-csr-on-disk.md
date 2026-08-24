# 提案：CSR 上磁盘 - L0 邻接表磁盘驻留以压缩 RSS

> track: poc
> 提出日期：2026-08-07
> 基线 Trunk：`346cd1c`
>
> Status: Rejected on 2026-08-07 (DEC-085: 性能恶化不可接受)

## 1. 调研洞察

### 1.1 问题：CSR 是 RSS 的第二大组件

SIFT1M 实测内存构成（512MB cgroup, sustained benchmark）：

| 组件 | 内存 | 占 init RSS | 处置 |
|------|------|-----------|------|
| 上层图+向量 | 30MB | 19% | 保留内存（搜索入口） |
| **CSR compact** | **47MB** | **30%** | **本提案目标** |
| CSR byte_offsets | 3.8MB | 2% | 保留内存（随机访问索引） |
| PQ codes | 30MB | 19% | 保留内存（Phase A 核心） |
| 其他（route/slot/BFS） | ~46MB | 29% | 保留内存 |
| **init RSS 合计** | **157MB** | 100% | |

CSR compact 是 init RSS 的 **30%**，是仅次于"其他"的第二大单一组件。

### 1.2 规模放大后 CSR 成为主瓶颈

| 规模 | CSR compact | 占预估 RSS | 当前 cgroup | 可行？ |
|------|------------|----------|------------|--------|
| 1M (SIFT) | 47MB | 30% | 256-512MB | ✅ 不是瓶颈 |
| 10M (DEEP) | 470MB | 29% | 2GB | ⚠️ 开始显著 |
| 100M (预估) | **4.7GB** | **>60%** | 任何合理 cgroup | ❌ 必须上磁盘 |

[[DEC-037]] 已记录 DEEP10M 核心数据 1.3GB > 1GB cgroup，其中 CSR = 591MB。
[[DEC-010]] 明确指出"100M 规模时 CSR 上磁盘是更有效的方案"。

### 1.3 CSR 访问模式分析

**当前代码路径**（`src/core/disk_hnsw.cpp:2749`）：
```
getInMemNeighbors(new_id) -> decodeCsrNeighbors(new_id)
  -> byte_start = adj_csr_byte_offsets_[new_id]
  -> 从 adj_csr_compact_.data() + byte_start 解码 delta+varint
  -> 输出到 thread_local csr_decode_buf_
```

**访问特征**：
- 每次搜索约 200-400 次 CSR 访问（EF=100-200, 每个被访问节点 1 次）
- 每次访问平均 49 bytes（21.2 条边 × 2.3 bytes/edge）
- **随机访问**（按 new_id 索引），但 BFS 重排使图相邻节点在文件中相邻
- 访问发生在 **Phase A**（PQ 粗筛），与 Phase B（vecblocks I/O）独立

**BFS 重排的局部性价值**：
- 4KB page 可容纳 ~83 个节点的 CSR entries
- 搜索路径上连续访问的节点通常图上相邻 -> BFS 重排后文件中也相邻
- 预期 page cache 命中率较高（具体需 R0 实测验证）

### 1.4 CSR I/O vs Phase B I/O 对比

| 维度 | Phase A (CSR) | Phase B (vecblocks) |
|------|-------------|-------------------|
| 每次访问大小 | ~49 bytes | 512 bytes (128-dim) |
| 每查询访问次数 | ~200-400 | ~50-100 |
| 每查询 I/O 量 | ~10-80 KB | ~25-50 KB |
| 访问模式 | 图引导随机 | 候选 ID 随机 |
| BFS 局部性 | ✅ 强（图相邻→文件相邻） | ✅ 强（BFS 块布局） |
| 现有优化 | 无（全在内存） | WILLNEED_BG + FVC + PAGE_MERGE_BG |

CSR 上磁盘后，Phase A 的 I/O 量与 Phase B 相当（甚至更大），
需要独立的 I/O 优化策略。

### 1.5 现有基础设施可复用

| 机制 | 可复用性 |
|------|---------|
| mmap + madvise | 直接可用（最简方案） |
| WILLNEED_BG SPSC 架构 | 可复用于 CSR 页预取 |
| BlockCache + LRU | 可扩展为 CSR 专用缓存 |
| cgroup_utils.sh | 可复用于 CSR page cache 记账 |

### 1.6 已有决策铺垫

- [[DEC-005]]: 选择 delta+varint 而非 BVGraph，理由之一是"随机访问友好"（`adj_csr_byte_offsets_` 提供 O(1) 定位）
- [[DEC-010]]: "100M 规模时 CSR 上磁盘是更有效的方案"
- [[DEC-026]]: P3（100M）需重新评估范式；CSR 上磁盘是图方法延续的前提
- [[DEC-037]]: DEEP10M CSR = 591MB，1GB cgroup 不可行
- 优化路线图 P3-1: "CSR 上磁盘 + 分页加载, 高复杂度, 🔴 优先级"

## 2. 方案方向

### 2.1 核心思路

将 `adj_csr_compact_`（47MB @ SIFT1M）从内存移到磁盘文件，
搜索时按需通过 page cache 读取。

**保留在内存**：`adj_csr_byte_offsets_`（3.8MB, 随机访问索引）、上层图+向量、PQ codes。
**移到磁盘**：`adj_csr_compact_`（压缩邻接表字节流）。

### 2.2 三种 I/O 路径（递进验证）

| 方案 | 复杂度 | 预取控制 | 适用场景 |
|------|--------|---------|---------|
| A. mmap (MADV_RANDOM) | 低（~20 行） | 无（内核管） | 快速验证可行性 |
| C. mmap + WILLNEED 预取 | 中 | 有（SPSC BG 线程） | 性能不达标时升级 |
| B. 分页 BlockCache | 高 | 完全控制 | 生产精细调优 |

建议 R0 先验证方案 A，按性能结果决定是否升级。

### 2.3 关键风险

1. **CSR page cache 与 vecblocks page cache 竞争**：两者共享 cgroup 预算，256MB 下可能互相挤压
2. **随机访问导致低命中率**：虽然 BFS 重排有帮助，但 HNSW 搜索路径的跳跃性可能使局部性不如预期
3. **mmap 在 cgroup 下的 page cache 记账**：需确认 cgroup v1/v2 下行为一致

## 3. 拟新增条款（draft, 待确认后落地）

### L0 CSR 邻接表磁盘驻留 {#BEH-036}
<!-- ndf: kind=req level=tbd layer=L1 status=draft since=0.9.12 source=proposed -->

L0 CSR 压缩邻接表 MAY 存储在磁盘文件中，搜索时按需通过 page cache 读取。
`adj_csr_byte_offsets_` MUST 保留在内存中。

### CSR 磁盘文件接口 {#API-020}
<!-- ndf: kind=interface level=tbd layer=L1 status=draft since=0.9.12 source=proposed -->

`CSR_FILE_PATH` 环境变量指定 CSR compact 文件路径。

## 4. 实验计划概要

| 轮次 | 内容 | 验收标准 |
|------|------|---------|
| R0 | mmap 基线 (SIFT1M 512/256MB sustained) | recall 不变; QPS 下降量化 |
| R1 | 性能分析 (mincore, majfault, I/O 量) | 瓶颈定位 |
| R2 | mmap + WILLNEED 预取 | QPS 恢复至 R0 的 90%+ |
| R3 | 256MB 极限内存验证 | QPS ≥ baseline 70% |
| R4 | DEEP10M 验证（如时间允许） | RSS 显著下降 |

## 5. 晋升条件

1. recall ≥ 95%（sustained, 不变）
2. QPS 下降 < 30%（512MB cgroup, vs CSR in-mem baseline）
3. RSS 下降 ≥ 40MB（SIFT1M）
4. 256MB cgroup 下可工作

## 6. 表面冲突检查

活跃 exploring 主题扫描：**无**（全部 promoted/rejected/closed）。
`explore_surface: graph-structure,io-path,memory-layout` 与已 promoted 主题不冲突。

## 7. 不做的事

- 不改 Trunk `src/`（POC 阶段）
- 不改上层图+向量、PQ codes、byte_offsets
- 不引入新压缩算法
- 不在 POC 阶段考虑 100M 规模（先 1M 验证可行性）
