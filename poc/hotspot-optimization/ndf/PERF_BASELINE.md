# Perf Baseline: hotspot-optimization

> topic_id: hotspot-optimization
> status: pending
> created: 2026-08-18
> links: TOPIC.md / DESIGN.md / spec/50-verification/golden-baseline.md

**非 SoT**。金标绑定头是比较身份；Numbers 仅在 R0 实测后由测量证据写入。
OpenClaw / binder MUST NOT 填写 Numbers。MUST NOT 从 SLA 或 NOTES 抄观测数字。

<!-- ndf:gate-slice begin=perf_bind -->
> vs: bl-trunk-golden-7ee4ee2
> config_id: cfg-m24-ef60
> measure_script: scripts/run_sustained.sh
> protocol: CON-SLA-014 strict cgroup + CON-SLA-019 禁预热 + CON-SLA-020 sustained

## Config

Inherit `spec/50-verification/configs/cfg-m24-ef60.md` (CON-GOLDEN C / DEC-087 Pareto).
Index pointer: `spec/50-verification/golden-baseline.md` current `bl-trunk-golden-7ee4ee2`.
Do not treat Config A/B as this bind. Extra 4T CPU hotspot notes (existing
`poc/multi-thread-scaling` evidence) are not this vs-bind and MUST NOT replace it.

## Measure

Executable entry: `scripts/run_sustained.sh --config cfg-m24-ef60`.
This slice is identity only. Do not put observations here.
<!-- ndf:gate-slice end=perf_bind -->

> trunk_sha: a14339234133cc6c5a2348464954f744c6465efb
> status: measured
> evidence_status: verified
> measured_trunk_sha: e37ab5e23a47dfb8a1d6167021d688d0dcd00d36

## Numbers

Measured 2026-08-22 under ACP lease `ep-c82a69ac-433a-4a36-a758-32674d616dd4`.
Protocol: CON-SLA-014 strict cgroup + CON-SLA-019 禁预热 + CON-SLA-020 sustained.
Config: cfg-m24-ef60 (M_graph=24, REFINE_EF=60, FLAT_VEC_MB=64), 512MB cgroup, 1T,
15 rounds x 1000 queries, seed=42, official 10K pool.

### R0 baseline (Trunk, no D1)

| metric | value |
|--------|------:|
| aggregate QPS | 2221.4 |
| steady QPS (Round 15) | 2679.3 |
| Recall@10 | 96.59% |
| RSS | 332 MB |

### R1 D1 (SIMD pqAdcDistance gather)

| metric | value |
|--------|------:|
| aggregate QPS | 2280.5 |
| steady QPS (Round 15) | 2733.9 |
| Recall@10 | 96.59% |
| RSS | 332 MB |

### Delta (D1 vs baseline)

| metric | baseline | D1 | delta |
|--------|---------:|---:|------:|
| aggregate QPS | 2221.4 | 2280.5 | **+2.66%** |
| steady QPS (R15) | 2679.3 | 2733.9 | **+2.04%** |
| Recall@10 | 96.59% | 96.59% | 0.00pp (unchanged) |

Teardown aborted with SIGABRT (rc=134, "terminate called without an active exception")
after full 15 rounds + aggregate printed; Numbers taken from printed aggregate + CSV_AGG.
Evidence: `ndf/evidence/poc_measurement-*.md` + `results/sustained/ver043_512mb_1t_n1000_r15.log`.
