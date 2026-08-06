# COMMITS: sustained-query-benchmark

> Topic: sustained-query-benchmark
> Baseline Trunk: `4a33f38`

## 2026-08-06 — POC 开题 + R0–R6 完整实验

**Topic:** sustained-query-benchmark
**Proposals:** `spec/open/proposal-sustained-query-benchmark.md`
**Clauses:** BEH-035 (draft), API-019 (draft)

### 新增文件

| 路径 | 说明 |
|------|------|
| `spec/open/proposal-sustained-query-benchmark.md` | POC 提案 |
| `poc/sustained-query-benchmark/ndf/TOPIC.md` | 装订器 |
| `poc/sustained-query-benchmark/ndf/proposals/draft-clauses.md` | BEH-035 / API-019 draft |
| `poc/sustained-query-benchmark/benchmark_sustained.cpp` | 多轮采样 benchmark |
| `poc/sustained-query-benchmark/Makefile` | 编译（链接未修改 Trunk src） |
| `poc/sustained-query-benchmark/run_sustained.sh` | 隔离运行脚本 |
| `poc/sustained-query-benchmark/ndf/evidence/r0-dataset-verification-20260806.md` | R0 |
| `poc/sustained-query-benchmark/ndf/evidence/r1-r2-saturation-20260806.md` | R1+R2 |
| `poc/sustained-query-benchmark/ndf/evidence/r3-r5-sweep-20260806.md` | R3+R4+R5 |
| `poc/sustained-query-benchmark/ndf/evidence/r6-hnswlib-comparison-20260806.md` | R6 |
| `data/sift_query_official10k.fvecs` | 官方 10K query 池 |
| `data/sift_groundtruth_official.ivecs` | 官方 GT |
| `data/sift_gt_official10k_k10.bin` | 官方 GT k=10 内部格式 |

### Trunk src 改动

**无**。本 POC 只改测量方法论，链接未修改的 Trunk `src/core/*.cpp`
（符合 [[BEH-018]] 第 6 条：探索期 MUST NOT 改 Trunk src）。

### 结果摘要

- 方法论有效：R=1 recall 精确匹配 baseline；稳态 QPS 与 N 无关；recall 96.00% ≥ 95%
- cache-warmed 高估 1.73–7.60×
- ADAPTIVE_EF 有效 (+12.5~31.4%)
- **GBDT 收益证伪** (−0.9~+1.8%)，根因为训练标签被 self-match 污染
- QPS/MB 内存效率优势不成立（0.17–0.33× hnswlib）

### 状态

TOPIC status: exploring → **ready-for-promote**
