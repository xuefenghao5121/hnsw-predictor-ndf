# PERF_BASELINE: ssd-parallelism-io

> baseline_id: bl-trunk-golden-434c6f5
> trunk_sha: 434c6f5
> short_sha: 434c6f5
> status: current
> measured: 2026-08-09
> protocol: CON-SLA-020 sustained, CON-SLA-014 strict cgroup, CON-SLA-019 禁预热
> config: cfg-m24-ef60 (M=24, EF=60)
> dataset: SIFT1M
> query: 官方 10K pool, 15 rounds × 1000, seed=42
> hardware: Intel i7-13700 (16C/24T), 32GB DDR4, NVMe SSD

## 金标基线 (Config C, 256MB, 1T)

| 指标 | 值 |
|------|-----|
| agg QPS | 1,450 |
| steady QPS | 1,702 |
| Recall@10 | 96.60% |

## 回归判定

- agg/steady 落在 ±2CV 内 = 无回归
- Recall 下降 > 0.3pp = 回归
- CV > 3% = 不可信，需重跑

## vs: 金标

- 脚本: `scripts/run_sustained.sh --config cfg-m24-ef60`
- baseline: bl-trunk-golden-434c6f5
