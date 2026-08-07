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

## 2. Pipeline 系统性约束

### 2.1 步骤依赖链

```
Step 1: build_index (M_graph, efC=200)
  ↓ M_graph 决定图的连通性, 影响所有后续步骤
Step 2: extract_graph (dim)
  ↓ 依赖 Step 1 的图
Step 3: bfs_reorder
  ↓ 依赖 Step 2 的图结构; BFS 映射是后续物理布局的基础
Step 4: write_blocks_veconly (BS)
  ↓ 依赖 Step 3 的 BFS 映射 + BS
Step 5: write_blocks + gen_route (BS)
  ↓ 依赖 Step 3 + BS; BS 必须与 Step 4 相同
Step 6: train_pq (M_pq)
  ↓ 依赖原始 base 数据 (不依赖图); M_pq 必须整除 dim
Step 7: gen_gt
  ↓ 独立
```

### 2.2 参数修改的级联影响

| 参数变更 | 需重做的步骤 | 不受影响 | 原因 |
|---------|-----------|---------|------|
| M_graph (16→32) | Step 1-5 | Step 6-7 | 图结构变了 → BFS 映射变了 → blocks/vecblocks 变了; PQ/GT 不依赖图 |
| M_pq (32→24) | Step 6 | Step 1-5, 7 | PQ 编码与图/blocks 独立 |
| BS (64K→32K) | Step 4-5 | Step 1-3, 6-7 | 仅物理布局变化; 图/BFS/PQ/GT 不变 |
| M_graph + M_pq | Step 1-6 | Step 7 | 两个独立变更的组合 |
| M_graph + BS | Step 1-5 | Step 6-7 | BFS 映射变了 → vecblocks 必须重建; BS 同时改变 |

### 2.3 系统性交互效应

参数间不仅有依赖关系，还有性能交互：

1. **M_graph × BS**: M↑ → 图更密 → BFS 局部性可能变化 → 影响 vecblocks page cache 命中率
2. **M_graph × M_pq**: M_graph↑ → 更好图连通性 + M_pq↓ → 更粗 PQ → recall 由两者共同决定
3. **M_pq × EF**: M_pq↓ → ADC recall↓ → 需更大 EF 补偿 → I/O↑ (抵消小 M_pq 的内存节省)
4. **BS × Fine Rerank**: Fine Rerank 读 4KB page，BS 影响物理布局和 readahead 局部性

**关键：不能独立调单个参数。必须联合考虑 recall = f(M_graph, M_pq, EF) 的三维空间。**

## 3. 调参空间（修订后优先级）

### P1: M_graph↑ 扫描（最高优先，DiskHNSW 独有链条）

建不同 M_graph 的图（16, 24, 32, 48），全套 pipeline 重建 Step 1-5。
固定 M_pq=32, BS=64K。

扫描：M_graph={16, 24, 32, 48} × EF={60, 80, 100, 120}
→ 找 recall-QPS Pareto 前沿
→ 核心验证：M↑ 能否通过 EF↓ 减少 I/O 提升 sustained QPS

### P2: M_pq 扫描 + OPQ 评估

在 P1 最优 M_graph 上，扫描 M_pq={24, 32, 48} + OPQ M=32。
仅需重做 Step 6。

→ 核心验证：DiskHNSW 双重回报（PQ↑ → recall↑ + I/O↓）
→ OPQ：离线训练旋转矩阵，推理零开销，+1-3% recall

### P3: BS 扫描（中优先）

在 P1+P2 最优组合上，扫描 BS={32K, 64K, 128K}。
需重做 Step 4-5。

→ 核心验证：BS 对 page cache 局部性的影响（预期收益有限）

### P4: 最优组合验证

P1+P2+P3 确定的最优组合，跑完整 sustained 矩阵。
对比：当前参数 vs 新参数的三方（BASE/ADAPTIVE/GBDT）表现。

## 3. 实验成本评估

分阶段剪枝（避免 4×4×4=64 组合爆炸）：

| 阶段 | 固定参数 | 扫描参数 | 需重建步骤 | 配置数 | 估时 |
|------|---------|---------|-----------|-------|------|
| P1 | M_pq=32, BS=64K | M_graph={16,24,32,48} × EF={60,80,100,120} | Step 1-5 | 4 pipeline × 4 EF × 2cg = 32 | ~3h |
| P2 | P1最优 M_graph, BS=64K | M_pq={24,32,48} + OPQ | Step 6 | 4方案 × 6config = 24 | ~1.5h |
| P3 | P1+P2最优 | BS={32K,64K,128K} | Step 4-5 | 3 pipeline × 6config = 18 | ~1.5h |
| P4 | P1+P2+P3最优 | 完整矩阵 | 无 | 6config | ~30min |

总重建次数：约 7 次 pipeline（P1: 4 + P3: 3）

## 4. 不做的事

- ~~M↓ (M=8, M=12)~~：方向反转，DiskHNSW 应试 M↑ 不是 M↓
- ~~PQ M↓ (M=16, M=24)~~：除非 OPQ M=24 能补偿 recall
- 不改 Fine Rerank page size（4KB 系统约束）
- 不改 efConstruction / BFS reorder

## 5. 表面冲突检查

无活跃 exploring 主题。`explore_surface: graph-structure,pq-encoding,block-layout` 不冲突。
