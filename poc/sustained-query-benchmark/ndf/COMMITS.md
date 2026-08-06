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

---

## 2026-08-06 — Promote 到 Trunk

**Topic:** sustained-query-benchmark
**Proposals:** `spec/open/proposal-promote-sustained-query-benchmark.md`
**Clauses:** BEH-035, API-019 (draft→stable); CON-SLA-019, CON-SLA-020,
MODEL-SUSTAINED-001, VER-043, VER-044, DEC-084 (new);
BEH-033, BEH-034 (must→may), API-018, CON-SLA-014/016/017/018 (amended)
**Promotes:** sustained-query-benchmark

| Kind | Commit | 说明 |
|------|--------|------|
| `src_commit` | `eee4ef7` | `src/benchmark/benchmark_sustained.cpp` + Makefile + `scripts/run_sustained.sh` |
| `spec_commit` | `eee4ef7` | 同一 commit（spec 与 src 一并合入） |

### Trunk 落点

| 路径 | 内容 |
|------|------|
| `src/benchmark/benchmark_sustained.cpp` | harness（自 poc 干净合入，补 CSV_AGG last_round_qps、Decay→Ramp-up 语义修正） |
| `Makefile` | `build/benchmark_sustained` 目标 + 加入 `BENCH` |
| `scripts/run_sustained.sh` | 隔离运行器（改用 `build/` 路径、`cg_stats_summary`、BEH-035 池来源校验） |
| `spec/20-behavior/test-infra.md` | `BEH-035` stable |
| `spec/30-interfaces/cli.md` | `API-019` stable |
| `spec/40-constraints/sla.md` | `CON-SLA-019` / `CON-SLA-020` + 口径标注 |
| `spec/models/sustained-query-measurement.md` | `MODEL-SUSTAINED-001` 语义核 |
| `spec/decisions/20-sustained-benchmark-methodology.md` | `DEC-084` |
| `spec/50-verification/acceptance-p2.md` | `VER-043` / `VER-044` |

### 验证

| 项 | 结果 |
|----|------|
| 编译 | ✅ `make build/benchmark_sustained` 通过（仅 Trunk 预存 warning） |
| VER-043 复现 | ✅ 512MB/1T/N=1000/R=15 → **1,482.6 QPS / 96.00% / unique 7,942** |
| vs POC 基线 | ✅ 1,482.6 vs 1,479.5（**0.2%**），recall 与 unique 精确一致 |
| graphcheck | ✅ **0 error**, 15 warning（全为预存 unlinked） |
| 条款计数 | 217 → **225** |

### 图修正

初次写入时 `BEH-035 depends-on API-019` 与 `API-019 depends-on BEH-035` 构成环
（graphcheck 报 1 error）。改为 `API-019 refines API-002`（行为条款单向持有依赖），
环消除。

### 基线失效（BEH-025 / §4c）

本主题 `baseline_status` → `stale`（Trunk 已移动）。
无其它活跃 exploring 主题，无需级联标注。
