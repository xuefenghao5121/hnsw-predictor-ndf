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
> status: pending
> evidence_status: pending

## Numbers

Pending R0. This mutable section may only be written from verified measurement evidence
joined to a Claude Code run/lease/completion. No QPS / recall figures are claimed yet.
