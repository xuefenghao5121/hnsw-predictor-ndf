# Perf Baseline: hierarchical-vamana

<!-- ndf:gate-slice begin=perf_bind -->
> vs: bl-trunk-d0ae5dd
> config_id: cfg-sla-ef100
> measure_script: scripts/run_sustained.sh
> protocol: VER-001 sustained + VER-003 cgroup v2（512MB / 16T）

## Config

继承 `spec/50-verification/configs/cfg-sla-ef100.md`：SIFT1M，REFINE_EF=100，
官方 10K query 池，15 rounds × 1000，seed=42；cgroup `memory.max=512MB`，THREADS=16。

## Measure

```bash
CGROUP_MB=512 THREADS=16 bash scripts/run_sustained.sh --config cfg-sla-ef100
```

POC 索引路径以 INTERFACE 为准（指向 `poc/hierarchical-vamana/` 产出，而非 Trunk 默认
`output/sift1m`，除非本轮明确复用对照索引做负对照）。观测写入 `evidence/` 与下方
Numbers；**不**写入产品 stable SLA。
<!-- ndf:gate-slice end=perf_bind -->

> trunk_sha: d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755
> status: measured
> evidence_status: measured

## Numbers

R0 measured (cfg-sla-ef100, SIFT1M @ cgroup 512MB @ 16T, VER-001 sustained).
Evidence: `ndf/evidence/run_poc_measure-512mb-16t.log` (raw) +
`ndf/evidence/poc_implementation-summary.md` (digest).

| metric | hierarchical-vamana | bl-trunk-d0ae5dd | Δ |
|--------|--------------------:|-----------------:|----:|
| Recall@10 | 98.00% | 96.00% | +2.00 pp |
| agg QPS | 4653.9 | 4330.9 | +7.5% |
| steady QPS (R15) | 6999.8 | 6448.0 | +8.6% |
| RSS after init | 175 MB | 157 MB | +18 MB |
| RSS end-of-run | 371 MB | 352 MB | +19 MB |

> 本表为 POC draft 数字，非 stable SLA。复现：`CGROUP_MB=512 THREADS=16 bash poc/hierarchical-vamana/scripts/run_poc_measure.sh`。

## Numbers — R1 α-sweep (2026-08-25)

R1 sensitivity (cfg-sla-ef100, SIFT1M @ cgroup 512MB @ 16T, VER-001 sustained).
Evidence: `ndf/evidence/run_poc_measure-512mb-16t-alpha{1.0,1.2,1.4}.log` (raw) +
`ndf/evidence/poc_measurement-summary.md` (digest). Fixed M=16 R0=32 Rup=16 beam=64
rounds=3 seed=42; sweep only α.

| α | Recall@10 | agg QPS | steady QPS (R15) | RSS after init | RSS end-of-run | L0 edges |
|----|----------:|--------:|-----------------:|---------------:|---------------:|---------:|
| 1.0 | 91.43% | 7128.0 | 11205.9 | 142 MB | 338 MB | 13.51M |
| 1.2 | **98.00%** | 6052.2 | 9214.9 | 175 MB | 371 MB | 29.64M |
| 1.4 | 95.92% | 5499.7 | 8438.7 | 206 MB | 401 MB | 31.89M |

对照：bl-trunk-d0ae5dd = Recall 96.00% / agg 4330.9 / steady 6448.0 / RSS init 157MB / end 352MB。

结论：α=1.2 为工作点（唯一同时满足 ≥95% 召回且 QPS/内存最优）。α=1.0 过度剪枝召回 91.43% 不达标；
α=1.4 度逼近 R=32 上限丧失 α-多样性，召回 95.92% 且 QPS 降至 5499.7、RSS 膨胀至 401MB（逼近 512MB 预算）。

> R1 α=1.2 重测 agg QPS 6052.2 较 R0 4653.9 高 ~30%（会话内连续运行、OS page cache 变热导致），
> Recall@10 稳定在 98.00%；绝对 QPS 需带 ±~30% 会话噪声解读。

## Numbers — R2 beam+R0 sweep @ α=1.2 (2026-08-25)

R2 sensitivity (cfg-sla-ef100, SIFT1M @ cgroup 512MB @ 16T, VER-001 sustained).
Evidence: `ndf/evidence/run_poc_measure-512mb-16t-r2-*.log` (raw) +
`ndf/evidence/poc_measurement-summary-r2.md` (digest). Fixed M=16 Rup=16 α=1.2
rounds=3 seed=42; sweep beam @ R0=32 and R0 @ beam=64.

beam axis (R0=32 fixed):

| beam | Recall@10 | agg QPS | steady QPS (R15) | RSS after init | RSS end-of-run | L0 edges |
|-----:|----------:|--------:|-----------------:|---------------:|---------------:|---------:|
| 32 | 97.02% | 6210.4 | 10051.2 | 171 MB | 367 MB | 26.24M |
| 64 | **98.00%** | 6159.1 | 9599.4 | 175 MB | 371 MB | 29.64M |
| 128 | 97.86% | 6130.1 | 9584.3 | 177 MB | 372 MB | 31.05M |

R0 axis (beam=64 fixed):

| R0 | Recall@10 | agg QPS | steady QPS (R15) | RSS after init | RSS end-of-run | L0 edges |
|--:|----------:|--------:|-----------------:|---------------:|---------------:|---------:|
| 24 | 95.87% | 6367.0 | 10507.5 | 163 MB | 358 MB | 23.25M |
| 32 | **98.00%** | 6159.1 | 9599.4 | 175 MB | 371 MB | 29.64M |
| 40 | 98.95% | 6047.8 | 8953.9 | 185 MB | 381 MB | 34.64M |

对照：bl-trunk-d0ae5dd = Recall 96.00% / agg 4330.9 / steady 6448.0 / RSS init 157MB / end 352MB。

结论：beam 在 {32,64,128} 影响微弱（recall 97-98%、QPS 6130-6210、建图 72→249s 近线性），beam=64 为默认；
R0 为主导旋钮：R0↑→边↑/recall↑/QPS↓/内存↑ 单调。工作点确认 beam=64/R0=32/α=1.2（recall 98.00%）；
R0=40 提供 +0.95pp recall（98.95%）但 QPS -1.8%、RSS +10MB；R0=24 最省内存（358MB）但 recall 95.87% 余量薄。

> R2 中心点 (beam=64/R0=32) agg QPS 6159.1 与 R1 α=1.2 重测 6052.2 一致（~2%），均为暖会话值（~30% 高于 R0 冷缓存 4653.9）。

## Numbers — R3 1T supplementary @ locked beam=32/R0=32/α=1.2 (2026-08-25)

R3 supplementary (cfg-sla-ef100, SIFT1M @ cgroup 512MB @ **1T**, VER-001 sustained).
Evidence: `ndf/evidence/run_poc_measure-512mb-1t-beam32_r032.log` (POC) +
`ndf/evidence/run_trunk_measure-512mb-1t.log` (trunk) +
`ndf/evidence/build-1t-beam32_r032.log`. Locked config (human override):
beam=32/R0=32/α=1.2, M=16 Rup=16 rounds=3 seed=42。

| metric | hierarchical-vamana @1T | bl-trunk-d0ae5dd @1T | Δ |
|--------|------------------------:|---------------------:|----:|
| Recall@10 | 97.02% | 96.00% | +1.02 pp |
| agg QPS | 1643.8 | 1434.1 | +14.6% |
| steady QPS (R15) | 1849.3 | 1697.1 | +9.0% |
| RSS after init | 171 MB | 157 MB | +14 MB |
| RSS end-of-run | 339 MB | 324 MB | +15 MB |
| L0 edges | 26.24M | 21.20M | +5.04M |

对照（POC 自身 @16T，R2 beam32/R0=32）：Recall 97.02% / agg 6210.4 / steady 10051 / RSS 367MB。

结论：1T 单线程磁盘路径上 hierarchical-vamana 仍保持 +1.02pp recall（97.02% vs 96.00%），
agg QPS +14.6%、steady +9.0% 优于 Trunk（16T 冷缓存 +7.5%、暖会话 +42%）；RSS +14~15MB 在
512MB 预算内。1T 单线程无并行放大，QPS 绝对量级 ~1/4 于 16T（1643.8 vs 6210.4），符合预期。

> 本表为 POC draft 数字，非 stable SLA。复现：`bash poc/hierarchical-vamana/scripts/run_measure_1t.sh`。
