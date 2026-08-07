# 提案：Pipeline 参数在 Sustained 口径下的优化空间（修订版）

> track: poc
> 提出日期：2026-08-07（修订）
> 基线 Trunk：`c63694f`
>
> Status: Proposed（等待人工确认）
> 修订说明：初版仅考虑"减内存"方向（M↓, PQ M↓）。用户指出需考虑 DiskHNSW 独特优势
> ——只有向量卸载才能使能的优化。修订后方向反转：**用被释放的内存预算投资 I/O 减少**。

## 1. 调研洞察

### 1.1 核心洞察：DiskHNSW 的独特优势

DiskHNSW 将向量卸载到磁盘，释放了 ~458MB 内存（SIFT1M：向量 488MB → PQ codes 30MB）。
这段被释放的内存可以**重新投资到减少 I/O 的方向**，这是全内存方案无法做到的。

**hnswlib 内存约束**：

| M | 内存/node | 向量占比 | M↑ 代价 |
|---|----------|---------|---------|
| 16 | 576B | 89% | 向量主导，M↑ 代价大 |
| 32 | 640B | 80% | +64B (图边), 但向量仍占 80% |

**DiskHNSW 内存约束**：

| M | 内存/node | 图占比 | M↑ 代价 |
|---|----------|-------|---------|
| 16 | 69B | 54% | 图边，M↑ 仅 +37B/node |
| 32 | 106B | 70% | 无向量代价! |
| 48 | 142B | 77% | 仍远小于 hnswlib 的 640B |

**关键区别**：hnswlib 中 M↑ 的代价包含向量增长（因为向量在内存）。
DiskHNSW 中 M↑ 只增加图边的内存，向量始终在磁盘。**M↑ 的代价在 DiskHNSW 中远小于 hnswlib。**

### 1.2 DiskHNSW 独有的优化链条

**链条 1：M↑ → EF↓ → I/O↓ → QPS↑**

```
更高图 M → 图更连通 → 同 recall 需要的 EF 更低
         → EF↓ → Phase A 候选数↓ → Phase B Fine Rerank I/O↓
         → I/O↓ → QPS↑
```

这在 hnswlib 中不存在（EF↓ 不减 I/O，因为向量全在内存）。
在 DiskHNSW 中 EF↓ **直接减少磁盘 I/O**。

**链条 2：PQ 质量↑ → I/O↓ 的双重回报**

```
标准 HNSW: PQ↑ → recall↑ (单一回报)
DiskHNSW:  PQ↑ → ADC recall↑
         → Phase A 候选集质量↑ (更少 false positive)
         → Phase B 每个 I/O 更可能读到 top-K 向量
         → 同 recall 可用更低 EF → I/O↓ → QPS↑
         → 双重回报: recall↑ + I/O↓
```

**链条 3：内存预算再分配**

被向量释放的 ~458MB 可投资到：
1. **更高图 M**（+37MB for M=32）→ 链条 1
2. **更好 PQ**（OPQ 或 M=48，+15MB）→ 链条 2
3. **更多 FVC**（+96MB）→ 减 page fault
4. **更多 page cache**（隐式）→ 减 majfault

问题：**最优分配是什么？**

### 1.3 量化分析

| 配置 | CSR (MB) | 图总内存 (MB) | 预估最低 EF | I/O/query (KB) | vs M=16/EF=100 |
|------|---------|-------------|-----------|---------------|----------------|
| M=16, EF=100 | 46 | 124 | 100 | 400 | baseline |
| M=24, EF=80 | 68 | 146 | ~80 | 320 | **-20%** |
| M=32, EF=70 | 92 | 170 | ~70 | 280 | **-30%** |
| M=48, EF=60 | 138 | 216 | ~60 | 240 | **-40%** |

> 注：EF 与 M 的关系需实测确定。表中 EF 为基于 HNSW 文献经验的粗略估计。

**M=32 的成本/收益分析（256MB cgroup）**：
- 成本：CSR +46MB = cgroup 预算的 18%
- 收益：如果 EF 100→70 可行，I/O -30%
- 256MB 下 page cache 预算减少 46MB，但 I/O 减少 30% 可能净赢

### 1.4 PQ 质量投资

| PQ 方案 | PQ codes (MB) | dist table (KB) | 预期 ADC recall 提升 | DiskHNSW 双重回报 |
|---------|-------------|----------------|---------------------|------------------|
| M=32（当前） | 30 | 32 (L1 fit) | baseline | - |
| OPQ M=32 | 30 | 32 | +1-3% | recall↑ + I/O↓ |
| M=48 | 45 | 48 (超 L1) | +2-4% | recall↑ + I/O↓, 但 dist table 超 L1 |
| OPQ M=24 | 24 | 24 | ~M=32 baseline | 省 6MB, 可能 OPQ 补偿 recall |

**OPQ（Optimized PQ）特别值得关注**：
- 离线训练一次性旋转矩阵，推理时零开销
- ADC recall +1-3% at same M
- 在 DiskHNSW 中通过链条 2 放大为 I/O 减少

## 2. 调参空间（修订后优先级）

### P1: HNSW M↑ 扫描（最高优先，方向反转）

建不同 M 的图（M=16, 24, 32, 48），在 sustained 下找 recall-QPS Pareto 前沿。

核心假设：M=24/32 能以更低的总 I/O（EF↓ 抵消 CSR↑）达到更高 QPS。

扫描：M={16, 24, 32, 48} × EF={60, 80, 100, 120} × 256/512MB

### P2: OPQ 评估（高优先，DiskHNSW 独有回报）

训练 OPQ 旋转矩阵，比较 OPQ vs PQ 在同 M 下的：
- ADC recall（离线评估）
- sustained QPS（Fine Rerank I/O 是否减少）

### P3: 内存预算最优分配（中优先）

在 P1+P2 确定的最优 M 和 PQ 方案上，扫描 FVC 和 page cache 分配。

### P4: Block size 扫描（低优先，预期收益有限）

Fine Rerank 已用 4KB page，block size 主要影响 vecblocks 物理布局。

## 3. 实验成本评估

| 实验 | 需重建 | 每配置 pipeline | 配置数 | 总时间 |
|------|--------|---------------|-------|-------|
| P1 (HNSW M) | 全套 pipeline | ~5min | 4M × 4EF × 2cg = 32 | ~3h |
| P2 (OPQ) | PQ only | ~5min (含 OPQ 训练) | 2方案 × 6config = 12 | ~1h |
| P3 (分配) | 无 | 0 | 6config | ~30min |
| P4 (Block) | blocks+vecblocks | ~3min | 4BS × 6config = 24 | ~2h |

P1 是最重投入但也最有潜力的实验。

## 4. 不做的事

- ~~M↓ (M=8, M=12)~~：方向反转，DiskHNSW 应试 M↑ 不是 M↓
- ~~PQ M↓ (M=16, M=24)~~：除非 OPQ M=24 能补偿 recall
- 不改 Fine Rerank page size（4KB 系统约束）
- 不改 efConstruction / BFS reorder

## 5. 表面冲突检查

无活跃 exploring 主题。`explore_surface: graph-structure,pq-encoding,block-layout` 不冲突。
