# 优化路线图 v3.0 (2026-08-06 更新)

> 基准: SIFT1M 30,332 QPS (16T 512MB) / 18,675 QPS (16T 256MB) / 95.75-95.80% recall
> 基准: DEEP10M 2,340 QPS (12T 2GB) / 95.15% recall / 1,612MB RSS
> 日期: 2026-08-06
> 关联: DEC-068~076, BEH-024~028, CON-SLA-014~018

## P2 完成状态

| # | 优化项 | 预期 | 实际 | 状态 | 条款 |
|---|--------|------|------|------|------|
| P0 | CSR 图裁剪 (Degree Cap) | RSS -22MB | recall -0.7pp, 不值 | ❌ 负结果 | DEC-038 |
| P1 | VisitedList uint32->uint8 | - | **2x QPS** | ✅ 最大收益 | DEC-034 |
| P2 | FINE_PREAD 修复 | - | recall 70%->95% | ✅ 关键修复 | DEC-035 |
| P3 | PQ dsub=3 SIMD | +20-50% QPS | +5% QPS | ✅ 小幅 | DEC-036 |
| P4 | flat_vec_cache | 256MB 7.5x | ✅ | ✅ promoted | DEC-068 |
| P5 | WILLNEED | 256MB 17.7x | ✅ | ✅ promoted | DEC-070 |
| P6 | FineRerank 线程安全 | 4T+ 稳定 | ✅ | ✅ promoted | DEC-073 |
| P7 | FVC 默认 64MB | +23.4% QPS | ✅ | ✅ promoted | DEC-073 |
| P8 | WILLNEED_BG (A2) | 16T +72.8% | ✅ | ✅ promoted | DEC-074 |
| P9 | VL_POOL (C2) | 12T +7.1% | ✅ | ✅ promoted | DEC-074 |
| P10 | PAGE_MERGE_BG | 256MB +17.5% | ✅ | ✅ promoted | DEC-075 |
| P11 | L4 cache 诊断 | Pareto 前沿 | ✅ | ✅ closed | BEH-024 |
| P12 | Fine Rerank io_uring | +5-20% QPS | -11~0% | ❌ 负结果 | DEC-076 |

## P2 最终成绩

```
SIFT1M (1M, 128D):
  512MB 16T: 30,332 QPS / 95.75% recall / RSS 242MB (QPS/MB 1.10x hnswlib)
  256MB 16T: 18,675 QPS / 95.80% recall / RSS 223MB (QPS/MB 1.36x hnswlib)

DEEP10M (10M, 96D), 2GB cgroup, T=12:
  Recall: 95.15% ✅
  QPS:    2,340  ✅
  RSS:    1,612MB (hnswlib OOM@2GB)
```

## 负结果记录

| POC | 方向 | 结果 | 教训 |
|-----|------|------|------|
| io-pipelining | pipe_ring_ 预取层 | rejected | WILLNEED 已取代 pipe |
| pq-quality | OPQ M=24 | rejected | OPQ 与 HNSW 图不兼容 |
| refine-ef-tuning | EF 调优 | rejected | EF=100 已最优 |
| l4-cache-mgmt | page cache 优化 | closed | Pareto 前沿 (3 promoted) |
| fine-rerank-iouring | io_uring 替代 pread | rejected | pread 不产生重复 I/O, io_uring 会 |

## 探索方向

| 方向 | 描述 | 优先级 | 状态 |
|------|------|--------|------|
| 自适应 EF (ADAPTIVE_EF) | PQ 距离间隙启发式 | ✅ 已完成 | [[BEH-033]] promoted, 200q +31% |
| Fine Rerank 早终止 | 连续无改善即停止 | ❌ 负结果 | [[DEC-081]] rejected (pread 架构下无效) |
| GBDT 学习式剪枝 (LEARNED_EF) | per-query 参数预测 | ✅ 已完成 | [[BEH-034]] promoted, 10Kq +33~124% |
| 200q cache-hit 修正 | benchmark 基准修正 | ✅ 已完成 | [[DEC-083]] + [[CON-SLA-019]] + [[CON-SLA-020]] |

## P3 路线图 (100M 规模)

| # | 优化项 | 目标 | 复杂度 | 优先级 | 条款 |
|---|--------|------|--------|--------|------|
| P3-1 | CSR 上磁盘 + 分页加载 | CSR 不占内存 | 高 | 🔴 | - |
| P3-2 | 1-hop CSR 预取 | 掩盖 CSR I/O | 中 | 🔴 | - |
| P3-3 | PQ codes mmap | -304MB RSS | 低 | 🟡 | - |
| P3-4 | 图裁剪 R_max=16-20 | 减 CSR 磁盘 I/O | 低 | 🟡 | DEC-038 |
| P3-5 | io_uring + O_DIRECT 重评估 | page cache 失效时 | 高 | ⚪ | DEC-076 |
| P3-6 | SPDK 评估 | I/O 带宽 | 高 | ⚪ | DEC-027 |

## 关键教训

1. **隐藏瓶颈 > 显式瓶颈**: VisitedList 分配 (隐藏) 比 PQ 计算 (显式 80%) 影响更大
2. **规模改变瓶颈**: 1M I/O 主导 -> 10M PQ 计算主导 -> 100M CSR 内存主导
3. **pread 优于 io_uring (buffered)**: pread 不产生重复 I/O, io_uring 与 readahead 冲突
4. **mutex 是多线程杀手**: A1 mutex 方案 8T -29%, A2 无锁方案 +21% (差距 50pp)
5. **NDF promote 必须按流程**: 跳步导致 ID 冲突、status 不一致、graphcheck 失败
