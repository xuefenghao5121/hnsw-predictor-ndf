# Baseline: bl-trunk-d0ae5dd

> baseline_id: bl-trunk-d0ae5dd
> trunk_sha: d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755
> short_sha: d0ae5dd
> status: stable
> measured: 2026-08-25
> protocol: [[VER-001]] sustained, [[VER-003]] cgroup v2 隔离, [[VER-006]] recall 验证
> dataset: SIFT1M
> query: 官方 10K pool, 15 rounds × 1000, seed=42
> config: cfg-sla-ef100
> clause: [[CON-SLA-001]]
> evidence: results/sustained/ver043_512mb_16t_n1000_r15.log

## Scene: SIFT1M @ cgroup 512MB @ 16T（cfg-sla-ef100）

| 指标 | 值 |
|------|-----|
| Recall@10 | **96.00%** |
| agg QPS | **4330.9** |
| steady QPS（Round 15） | **6448.0** |
| Round 1 QPS（ramp-up 起点） | 1084.0 |
| Ramp-up | 494.8% |
| 常驻内存（RSS after init） | 157 MB |
| 峰值内存（anon RSS） | 352 MB |
| cgroup `memory.peak` | 512 MB（`oom=0`，`max` 事件 8368 次触顶回收） |

> 内存口径：cgroup v2 `memory.peak` = anon + file（page cache）。本场景 anon 352MB +
> 页缓存触顶 512MB 预算，内核通过页缓存回收避免 OOM（`oom=0`），符合 [[CON-001]]。

## 复现

```bash
CGROUP_MB=512 THREADS=16 bash scripts/run_sustained.sh --config cfg-sla-ef100
```

产出 log：`results/sustained/ver043_512mb_16t_n1000_r15.log`。

## 备注

- `benchmark_sustained` 在打印 `CSV_AGG` 与 `=== Aggregate ===` 后、进程退出阶段抛
  `terminate called without an active exception`（SIGABRT），不影响已打印的全部测量值
  （15 轮 + aggregate + recall 均完整）。属已知 teardown 缺陷，测量数字有效。
- 与既有 `results/sustained/official_512mb_16t_n1000_r15.log`（agg 4255.4 QPS / 96.00%
  recall）同口径一致，差异 ~1.8%（运行噪声）。
