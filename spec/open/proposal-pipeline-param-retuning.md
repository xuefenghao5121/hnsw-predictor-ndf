# 提案：Pipeline 参数在 Sustained 口径下的优化空间

> track: poc
> 提出日期：2026-08-07
> 基线 Trunk：`c63694f`
>
> Status: Proposed（等待人工确认）

## 1. 调研洞察

### 1.1 核心问题

继 `sustained-param-retuning`（搜索调参）之后，本提案关注 **pipeline 构建参数**。
这些参数在建图/分块/PQ 编码阶段确定，影响图结构、磁盘布局、内存占用，
进而影响 sustained 性能。

所有 pipeline 参数的最优值均来自早期实践或 cache-warmed 口径，sustained 下从未验证。

### 1.2 Pipeline 参数审计

| 参数 | 当前值 | 确定依据 | 口径 | 影响机制 | Sustained 重测？ |
|------|--------|---------|------|---------|----------------|
| **Block size** | 64KB | DEC-008 硬编码 | cache-warmed | BlockCache 粒度 + BFS 布局 | ❌ |
| **HNSW M** | 16 | hnswlib 默认 | N/A (建图) | CSR 大小 + recall + 搜索计算量 | ❌ |
| **HNSW efConstruction** | 200 | hnswlib 默认 | N/A (建图) | 图质量 | ❌ |
| **PQ M** | 32 | DEC-014 (L1 fit) | cache-warmed | PQ codes 内存 + ADC recall | ❌ |
| **Fine Rerank page** | 4KB | DEC-009 | cache-warmed | Phase B I/O 粒度 | ❌ |

### 1.3 各参数在 sustained 下的影响分析

#### Block size (64KB)

**当前路径**：Fine Rerank (FINE_RERANK=1) 读 4KB page，已绕过 64KB block 粒度。
block size 主要影响：
1. **vecblocks 文件物理布局**：大 block = 更多 BFS 相邻节点在同一文件区域 = 更好的 kernel page cache 局部性
2. **BlockCache 效率**：Phase A fallback 路径（FINE_RERANK=0 时），但生产环境都开 FINE_RERANK=1
3. **readahead 粒度**：kernel 默认 readahead 以 page (4KB) 为单位，block size 不直接影响

**sustained 假设**：block size 从 16KB 到 256KB 可能影响 page cache 局部性，但因 Fine Rerank 已用 4KB page，影响可能有限。

**实验价值**：中。值得扫描但预期收益不大。

#### HNSW M (16)

**当前值 M=16**：hnswlib maxM0 = 2×16 = 32，实际 avg 21.2 edges/node。

M 影响：
1. **CSR 大小**：线性正比（M=8 → CSR ~22MB, M=16 → 47MB, M=24 → 68MB）
2. **ADC recall**：更多边 = 更好的图连通性 = 更高 recall
3. **Phase A 计算量**：更多邻居 = 更多 PQ ADC 距离计算
4. **sustained 关键**：CSR 在内存中，小 M = 省 CSR 内存 = 更多 page cache 给 vecblocks

**sustained 假设**：
- **M=12**：CSR ~33MB (-14MB)，recall 可能下降但可用更大 EF 弥补。省下的 14MB 内存给 page cache。
- **M=8**：CSR ~22MB (-25MB)，recall 下降显著，可能需要 EF=150+ 补偿，反而增加 I/O。
- M=16 可能仍是平衡点，但值得验证 M=12。

**实验价值**：高。M 直接影响内存布局和 recall-I/O 权衡，sustained 下可能有不同最优点。

#### PQ M (32)

**当前值 M=32**：PQ codes 30MB，dist table 32KB（L1 fit）。

PQ M 影响：
1. **PQ codes 内存**：M=32 → 30MB, M=24 → 24MB (-6MB), M=16 → 16MB (-14MB)
2. **ADC recall**：小 M = 更粗糙的距离近似 = 更低 recall
3. **dist table 大小**：M=32 → 32KB (L1 fit), M=24 → 24KB, M=16 → 16KB
4. **sustained 关键**：PQ codes 在内存，小 M 省内存但 recall 降

**sustained 假设**：
- M=32 的 L1 cache fit 是性能甜点（DEC-014），sustained 下可能仍成立
- 但省 6-14MB 内存在 256MB cgroup 下有意义
- recall 下降可用 EF 弥补（M=24 + EF=120 vs M=32 + EF=100）

**实验价值**：中高。PQ M=24 值得验证。

#### Fine Rerank page size (4KB)

**当前值 4KB**：DEC-009 确定，比 64KB block 减少 128x I/O。

**sustained 影响**：4KB 是 Linux page size，无法更小。2KB sub-page 被否决（需用户态拼接）。
8KB/16KB 会增加 I/O 放大。

**结论**：4KB 是系统约束，无优化空间。不改。

#### HNSW efConstruction (200)

**影响**：仅影响建图质量（图的连通性），不影响搜索参数。200 是 hnswlib 默认值，
已足够好。更高值（500）建图慢但图质量略好，对 sustained 无直接影响。

**结论**：不改。

## 2. 调参空间（按优先级）

### P1: HNSW M 扫描（最高优先）

建不同 M 的图（M=8, 12, 16, 24），测量 sustained 性能。

需重建 graph + blocks + vecblocks + PQ（全套 pipeline）。
每个 M 需跑一次完整 pipeline + sustained benchmark。

扫描范围：{8, 12, 16, 24}
- recall 约束：≥ 95%
- 关注 256MB：小 M 省 CSR = 更多 page cache = 可能 +QPS

### P2: PQ M 扫描（高优先）

建不同 M 的 PQ codes（M=16, 24, 32），测量 sustained 性能。

仅需重新训练 PQ，不需重建图/blocks。
但不同 PQ M 影响 ADC recall，需重新校准 EF。

扫描范围：{16, 24, 32}
- 配合 P1 的最优 M 一起测

### P3: Block size 扫描（中等优先）

建不同 block size 的 vecblocks（16KB, 32KB, 64KB, 128KB），测量 sustained 性能。

需重建 blocks + vecblocks + route（但不需重建图和 PQ）。

扫描范围：{16384, 32768, 65536, 131072}
- 预期影响有限（Fine Rerank 已用 4KB page）

### P4: 组合优化

P1+P2 确定的最优 M + PQ M 组合，跑完整 sustained 矩阵。

## 3. 实验成本评估

| 实验 | 需重建 | 每配置耗时 | 配置数 | 总时间 |
|------|--------|----------|-------|-------|
| P1 (HNSW M) | 全套 pipeline | ~5min pipeline + ~3min/bench | 4M × 6config = 24 | ~120min |
| P2 (PQ M) | PQ only | ~2min PQ + ~3min/bench | 3M × 6config = 18 | ~90min |
| P3 (Block size) | blocks + vecblocks | ~3min + ~3min/bench | 4BS × 6config = 24 | ~120min |
| P4 (组合) | 无（用 P1/P2 最优） | ~3min/bench | 6config | ~18min |

## 4. 关键风险

1. **M 改变需重建全套数据**：graph + blocks + vecblocks + PQ，工作量大
2. **PQ M 改变需重新校准 EF**：小 M = 低 recall = 需更大 EF = 更多 I/O
3. **Block size 改变需重建 blocks + vecblocks**：但不影响图和 PQ
4. **跨参数交互**：M 和 PQ M 有交互（图连通性 × PQ 精度），需联合调优

## 5. 表面冲突检查

无活跃 exploring 主题（sustained-param-retuning 刚 promoted）。
`explore_surface: graph-structure,pq-encoding,block-layout` 与已 promoted 主题不冲突。

## 6. 不做的事

- 不改 Fine Rerank page size（4KB 是系统约束）
- 不改 efConstruction（不影响搜索）
- 不改 BFS reorder（DEC-006 已确定，无替代方案）
- 不在 POC 阶段考虑 DEEP10M / 100M（先 SIFT1M 验证）
