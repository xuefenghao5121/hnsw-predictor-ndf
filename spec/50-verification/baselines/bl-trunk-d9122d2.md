# Baseline: bl-trunk-d9122d2

> baseline_id: bl-trunk-d9122d2
> trunk_sha: d9122d266a33e11a033e4c3a02589e9c2359ab2b
> short_sha: d9122d2
> status: stable
> measured: 2026-08-25
> protocol: [[VER-001]] sustained, [[VER-003]] cgroup v2 隔离, [[VER-006]] recall 验证
> dataset: SIFT1M
> query: 官方 10K pool, 15 rounds × 1000, seed=42
> config: cfg-sla-ef100
> clause: [[CON-SLA-001]]
> promotes: hierarchical-vamana（分层 Vamana 默认建图，[[BEH-027]] / [[ARCH-007]]）
> evidence: results/sustained/hv_promote_512mb_16t_n1000_r15.log

## Scene: SIFT1M @ cgroup 512MB @ 16T（cfg-sla-ef100）

| 指标 | 值 |
|------|-----|
| Recall@10 | **97.02%** |
| agg QPS | **5708.4** |
| steady QPS（Round 15） | **9035.3** |
| Round 1 QPS（ramp-up 起点） | 1298.8 |
| Ramp-up | 595.7% |
| 常驻内存（RSS after init） | 170 MB |
| 峰值内存（RSS end-of-run） | 367 MB |

> 相对旧金标 bl-trunk-d0ae5dd（hnswlib 建图，Recall 96.00% / agg 4330.9 / steady 6448.0）：
> Recall +1.02pp，agg QPS +31.8%，steady QPS +40.1%，RSS init +13MB / end +15MB（仍 512MB 预算内）。

## 复现

```bash
bash scripts/build_pipeline.sh data/sift_base.fvecs sift1m 32
CGROUP_MB=512 THREADS=16 bash scripts/run_sustained.sh --config cfg-sla-ef100
```

产出 log：`results/sustained/hv_promote_512mb_16t_n1000_r15.log`。

## 备注

- 建图入口已由 hnswlib 整图建边替换为分层 Vamana（`build_index` 直接产出 GraphStructure，
  原 `extract_graph` 步骤并入）；锁定运行点 `M=16 R0=32 Rup=16 beam=32 α=1.2 rounds=3 seed=42`。
- `benchmark_sustained` 在打印 `CSV_AGG` 与 Aggregate 后、进程退出阶段抛
  `terminate called without an active exception`（SIGABRT），属已知 teardown 缺陷，
  不影响已打印的 15 轮 + aggregate + recall 测量值（见 bl-trunk-d0ae5dd 备注）。
