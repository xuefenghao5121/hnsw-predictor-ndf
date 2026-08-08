# TOPIC: pipeline-param-retuning

> topic_id: pipeline-param-retuning
> status: exploring
> baseline_protocol: [[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]] (sustained)
> baseline_trunk_sha: c63694f
> baseline_status: stale (R0-R5 旧数据废弃, env 配置错误)
> explore_surface: graph-structure,pq-encoding,block-layout
> depends_on_topics: sustained-param-retuning (promoted), gbdt-retrain (promoted)
> conflicts_with_topics: []
> binder: [[DEF-022]]
> opened: 2026-08-07

## 目标

在 sustained 口径下联合调优 pipeline 三参数 (M_graph, M_pq, BS)，
利用 DiskHNSW 独有优势（向量卸载使能的 M↑ -> EF↓ -> I/O↓ 链条）。

## 背景

Pipeline 7 步相互配套：M_graph 变需重建 Step 1-5，M_pq 变需重做 Step 6，
BS 变需重建 Step 4-5。不能独立调参。

DiskHNSW 独有优化链条：
1. M↑ -> 图更连通 -> EF↓ -> I/O↓ -> QPS↑ (hnswlib 无此链条)
2. PQ↑ -> 双重回报 (recall↑ + I/O↓)
3. 内存预算再分配 (向量释放 458MB 投资到 I/O 减少)

## Active hypothesis

M_graph↑ (16->24/32) 通过 EF↓ 减少 I/O，在 sustained 下净 QPS 提升，
CSR 增大的内存代价被 I/O 减少抵消。

## ⚠️ 旧数据废弃说明 (2026-08-08)

R0-R5 全部 QPS 数据废弃，原因：
1. 测试脚本缺少 `L4_WILLNEED=1`（256MB 下 17.7x QPS 影响，[[DEC-070]]）
2. 测试脚本缺少 `PAGE_MERGE_BG=1`（CON-SLA-020 标准配置）
3. M=16 EF=100 1T 256MB 实测 146 QPS vs CON-SLA-020 基线 1,076 QPS（差 7.4x）

Recall 数据仍有效（不受 I/O 优化影响）。

双基线对照：
- **BASE 基线**: M=16, EF=100, ADAPTIVE_EF=0 -> 对齐 CON-SLA-020
- **ADAPTIVE 基线**: M=16, EF=90, ADAPTIVE_EF=1, eef=40 -> 对齐 DEC-086 最优

## 实验计划

| 阶段 | 固定 | 扫描 | 重建步骤 | 验收 |
|------|------|------|---------|------|
| R0' | M_pq=32, BS=64K | M_graph={16,24,32,48} × EF={60,80,100,120} 1T | Step 1-5 | Pareto 前沿 (BASE) |
| R1' | R0'最优 | GBDT/ADAPTIVE 1T | - | ADAPTIVE 增量 |
| R2' | R0'最优 | M_pq={16,32,64} 1T | Step 6 | PQ 双重回报 |
| R3' | R0'最优 | T={4,8,16} | - | 多线程扩展 |
| R4' | R0'最优 | BS={32K,64K,128K} 1T | Step 4-5 | BS 局部性影响 |
| R5' | 完整 strict 256MB 复验 + ADAPTIVE 基线对比 | - | - | 最终验证 |

## 标准配置（对齐 CON-SLA-020 + DEC-086）

**BASE 模式（扫描用）**:
```bash
CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
FLAT_VEC_MB=64 ADAPTIVE_EF=0
```

**ADAPTIVE 模式（复验用，对齐 DEC-086）**:
```bash
# 同上，但：
REFINE_EF=90 ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=40
```

## Draft clauses

无新增条款。本 POC 目标是修改现有 pipeline 默认参数（若发现更优组合）。

## 写入边界

- 本 POC MUST NOT 修改 Trunk `src/`（[[BEH-018]] 第 6 条）
- 不同 M_graph 的数据放在独立目录（如 `output/sift1m_m24/`）
- 使用 Trunk `build/benchmark_sustained`

## 表面冲突检查

无活跃 exploring 主题。已 promoted 主题与本主题为依赖关系，不冲突。
