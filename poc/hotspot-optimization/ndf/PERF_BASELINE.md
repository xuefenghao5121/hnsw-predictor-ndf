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
> measured_trunk_sha: f7901cc18dd5ac707303b656a6a284918821f13c

## Numbers

Measured 2026-08-21 under ACP lease `ep-93fcfbef-fce3-4d37-8f7e-eabc349cc4ac`
(attempt `ca511456-6886-4bbe-9a2c-c27f0ee65be2`).
Protocol: CON-SLA-014 strict cgroup + CON-SLA-019 禁预热 + CON-SLA-020 sustained.
Config: cfg-m24-ef60 (M_graph=24, REFINE_EF=60, FLAT_VEC_MB=64), 512MB cgroup, 1T,
15 rounds × 1000 queries, seed=42, official 10K pool.

| metric | value |
|--------|------:|
| aggregate QPS | 2221.4 |
| steady QPS (Round 15) | 2679.3 |
| Recall@10 | 96.59% |
| RSS | 332 MB |
| ramp-up (R1→R15) | 171.7% |
| cumulative unique queries | 7942 / 10000 |
| total time (15K queries) | 6.752 s |

Teardown aborted with SIGABRT (rc=134, "terminate called without an active exception")
after the full 15 rounds + aggregate printed; Numbers are taken from the printed aggregate
and CSV_AGG. Evidence: `ndf/evidence/r0-measurement-20260821.md` +
`results/sustained/ver043_512mb_1t_n1000_r15.log`.
