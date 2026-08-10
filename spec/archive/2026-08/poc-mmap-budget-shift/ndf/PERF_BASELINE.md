# Perf baseline — mmap-budget-shift

> trunk_sha: 3e98f3e  
> config_id: cfg-sla-ef100, cfg-adaptive-ef90, cfg-m24-ef60  
> protocol: [[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]]  
> status: current  
> vs: bl-trunk-golden-434c6f5

## Config

- 默认对照黄金三组：  
  [`cfg-sla-ef100`](../../../spec/50-verification/configs/cfg-sla-ef100.md)、  
  [`cfg-adaptive-ef90`](../../../spec/50-verification/configs/cfg-adaptive-ef90.md)、  
  [`cfg-m24-ef60`](../../../spec/50-verification/configs/cfg-m24-ef60.md)
- R0 计划：A/B 金标对比（TOPIC 验证计划）

## Numbers

沿用 Trunk 金标表：[`bl-trunk-golden-434c6f5`](../../../spec/50-verification/baselines/bl-trunk-golden-434c6f5.md)

本主题尚未在 `3e98f3e` 重测独立 R0；Δ% 叙事相对上述 `vs` 卡。重测后替换本节约为
cgroup × threads × agg/steady/recall 表，并保持 `trunk_sha` 与 TOPIC
`baseline_trunk_sha` 一致。

## Notes

样板卡（[[META-007]]）。金标 trunk `434c6f5` 与主题钉扎 `3e98f3e` 不同：继续测量前
若需现行 Trunk 叙事，按 [[BEH-025]] 重测 R0 或 evidence 标 `vs_trunk=434c6f5`。
