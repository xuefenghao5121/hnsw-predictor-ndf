# DEC-094: mmap Anon→File 预算转移负结果 — Page Cache Thrashing {#DEC-094}

> date: 2026-08-10
> topic: mmap-budget-shift
> Rejects: mmap-budget-shift
> affects: DEC-088, BEH-024, BEH-027
<!-- ndf: depends-on=DEC-088,DEC-064,DEC-034 -->

## 背景

R0 speculative-prefetch + R0 data-layout 两个 POC 均 rejected 后，
用户提出新方向：cgroup memory budget = anon + file，
可将 read-only 数据结构从 anon (vector) 改为 file (mmap)，释放 anon 预算换取 page cache。

DEC-088 因果模型：
```
anon = upper_vectors + CSR + PQ_codes + FVC + BlockCache + VisitedList
file = cgroup_limit - anon  (page cache for vecblocks)
```

## 审计修正

提案初始版本有 4 个错误，在审计中修正：
1. **Upper vectors**: 声称 30MB 可 mmap，实际 kUpperPQ=1（默认，DEC-034）已释放，稳态 0MB
2. **PQ codes**: 声称 30MB，实际 M_pq=32（非 M_graph=24），30.5MB
3. **CSR**: 声称 47MB 原始，实际 Delta+Varint 压缩（DEC-064），57MB (54MB compact + 3MB offsets)
4. **baseline_trunk_sha**: 3e98f3e → 434c6f5（与金标一致，src/ 相同）

修正后可 mmap 总量：87MB (PQ 30MB + CSR 57MB)，预期 page cache ~4x（非 5x）。

## R0: PQ codes mmap (30MB)

脚本: `scripts/run_sustained.sh` (CON-SLA-020 金标)
配置: Config C (DEC-087: M=24, EF=60), 256MB 1T, 15轮×1000q, seed=42

| | A (vector PQ) | B (mmap PQ) | Delta |
|--|:---:|:---:|:---:|
| agg QPS | 1,431.6 | 277.0 | **−80.6%** |
| steady QPS | 1,662.7 | 267.4 | **−83.9%** |
| recall | 96.60% | 96.60% | 0 ✅ |
| Ramp-up | 167.5% | 5.0% | mmap 无法热身 |

A vs 金标 1,450: −1.3%（±2CV 内 ✅）

## R1: CSR mmap (57MB)

脚本/配置同 R0。

| | A (vector CSR) | B (mmap CSR) | Delta |
|--|:---:|:---:|:---:|
| agg QPS | 1,427.7 | 480.6 | **−66.3%** |
| steady QPS | 1,638.3 | 495.5 | **−69.8%** |
| recall | 96.60% | 96.60% | 0 ✅ |

A vs 金标 1,450: −1.5%（±2CV 内 ✅）

## 根因分析

mmap 将 read-only 数据从 anon 转为 file-backed，确实释放了 anon 预算。
但 file-backed 数据在 page cache 中与 vecblocks 争夺空间：

| 数据结构 | 大小 | 访问模式 | 退化幅度 |
|----------|------|----------|---------|
| PQ codes | 30MB | 纯随机, 每 candidate 32B | −80.6% |
| CSR | 57MB | BFS 局部性, varint ~2B/edge | −66.3% |

CSR 的 BFS 局部性使退化幅度比 PQ codes 轻（−66% vs −80%），
但 57MB file-backed 面积更大，净效果仍然严重负。

**PQ codes Ramp-up 仅 5%**：mmap page fault 贯穿全部 15 轮，
说明 kernel LRU 无法有效管理混合工作负载（hot 小量随机 + warm 大量随机）。

## 结论

mmap anon→file 预算转移方向**证伪**。

释放 anon 预算的代价是 file-backed 数据自身争夺 page cache，
净效果为严重负（−66~−80% QPS）。

与 [[DEC-067]]（R5c mincore 诊断）结论一致：
**页缓存在 Pareto 前沿**，anon/file 分配已是最优。

## 不改的项

- 不改 Trunk `src/`
- 不改 SLA 阈值
- 不改现有 API 参数默认值

## 来源

- 提案: `spec/archive/2026-08/poc-mmap-budget-shift/proposal-poc-mmap-budget-shift.md`
- TOPIC: `spec/archive/2026-08/poc-mmap-budget-shift/ndf/TOPIC.md`
- NOTES: `spec/archive/2026-08/poc-mmap-budget-shift/NOTES.md`
- R0 evidence: `spec/archive/2026-08/poc-mmap-budget-shift/results/r0_*.log`
- R1 evidence: `spec/archive/2026-08/poc-mmap-budget-shift/results/r1_*.log`
