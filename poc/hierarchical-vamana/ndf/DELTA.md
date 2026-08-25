# DELTA.md — hierarchical-vamana

> topic_id: hierarchical-vamana
> status: draft
> links: TOPIC.md / DESIGN.md / PERF_BASELINE.md

<!-- ndf:gate-slice begin=delta_hypothesis -->
## Bind snapshot

| leg | id / path |
|-----|-----------|
| vs | bl-trunk-d0ae5dd |
| config_id | cfg-sla-ef100 |
| measure_script | scripts/run_sustained.sh |

## Feature delta

| id | change | links | status |
|----|--------|-------|--------|
| F1 | 建图：HNSW 层分配 + 层内 Vamana RobustPrune，替换 hnswlib 整图建边 | BEH-HV-001 / DESIGN | implemented |
| F2 | 导出邻接到现 DiskHNSW reorder/blocks/PQ（或明确迁移） | ARCH-HV-001 / DESIGN | implemented |
| F3 | 搜索：上层内存下降 + 现 L0 Fine Rerank（最小适配） | DESIGN §flow | implemented |

## Hotspot delta

| id | hypothesis | measured | links | status |
|----|------------|----------|-------|--------|
| H1 | Vamana α 剪枝减少无效边 → 同等召回下更高 QPS 或更低跳数 | measured | PERF / evidence | resolved |
| H2 | 上层稀疏导航缩短进入 L0 的路径 | measured | PERF / evidence | resolved |
| H3 | 建图 CPU 时间可能高于 hnswlib；可接受若查询收益明显 | measured | evidence | resolved |
<!-- ndf:gate-slice end=delta_hypothesis -->

## Rounds

| round | date | bind unchanged? | feature notes | hotspot notes | conclusion |
|-------|------|-----------------|---------------|---------------|------------|
| R0 | 2026-08-25 | yes (vs=bl-trunk-d0ae5dd) | F1+F2+F3 落地，导出 GraphStructure 复用 Trunk 后段管线 | H1/H2/H3 测出：Recall 98.00% vs 96.00% (+2pp)，agg QPS 4653.9 vs 4330.9 (+7.5%)，steady +8.6%；RSS +18MB | Vamana α 剪枝带来更长程、更少无效边 → 同/更高召回 + 更高 QPS，代价是 delta 压缩变差（+18MB）。H0 初步成立 |
| R1 | 2026-08-25 | yes (vs=bl-trunk-d0ae5dd) | α∈{1.0,1.2,1.4} 敏感度扫描 @16T（M=16 R0=32 Rup=16 beam=64 rounds=3 seed=42，无 1T 补充） | α=1.0：Recall 91.43%（<95% 失败）/ agg 7128.0；α=1.2：Recall **98.00%** / agg 6052.2 / steady 9214.9；α=1.4：Recall 95.92% / agg 5499.7 / RSS 401MB | α=1.2 为工作点：α 过低→过度剪枝召回崩塌；α 过高→度逼近 R=32 丧失 α-多样性，召回与 QPS 双降且内存膨胀。详见 ndf/evidence/poc_measurement-summary.md |
| R2 | 2026-08-25 | yes (vs=bl-trunk-d0ae5dd) | beam∈{32,64,128}@R0=32 + R0∈{24,32,40}@beam=64 扫描 @16T（α=1.2, M=16 Rup=16 rounds=3 seed=42，无 1T） | beam：Recall 97.02/98.00/97.86%，agg 6210.4/6159.1/6130.1（近平坦，beam=64 recall 最优）；R0：Recall 95.87/98.00/98.95%，agg 6367.0/6159.1/6047.8，RSS 358/371/381MB，L0 边 23.25/29.64/34.64M | beam 在 {32,64,128} 影响微弱（recall 97-98%、QPS 6130-6210），建图近线性（72→249s）；R0 为主导旋钮：R0↑→边↑/recall↑/QPS↓/内存↑ 单调。工作点确认 beam=64/R0=32/α=1.2（recall 98.00%）；R0=40 提供 +0.95pp recall（98.95%）但 QPS -1.8%、RSS +10MB；R0=24 最省内存（358MB）但 recall 95.87% 余量薄。详见 ndf/evidence/poc_measurement-summary-r2.md |
| R2b | 2026-08-25 | yes (vs=bl-trunk-d0ae5dd) | Control binder_amend：INTERFACE `interface_contract` 钉死默认（HV_M=16 R0=32 Rup=16 **beam=32** α=1.2 rounds=3 seed=42）；无代码/测量变更 | 人类 override R2 agent 选 beam=64：固定 beam=32/R0=32/α=1.2（Recall 97.02% / agg 6210.4 / RSS 367MB vs beam=64 98.00%/6159.1/371MB） | −0.98pp recall 换更高 QPS + 略省 RSS + 建图快 ~1.9×（72s vs 136s）；仍 ≥95% H0 成立。perf_bind 协议不变（512MB/16T）。代码默认值待下一「派发」实现步落地 |
| R3 | 2026-08-25 | yes (vs=bl-trunk-d0ae5dd) | 1T 补充测量 @ locked beam=32/R0=32/α=1.2（M=16 Rup=16 rounds=3 seed=42）；无代码变更，仅 build wrapper 钉死 HV_BEAM=32（代码默认仍 64，待实现步落地） | POC @1T：Recall 97.02% / agg 1643.8 / steady 1849.3 / RSS 171→339MB；Trunk @1T：96.00% / 1434.1 / 1697.1 / 157→324MB | 1T 单线程下 POC 仍 +1.02pp recall、agg +14.6%、steady +9.0% vs Trunk；RSS +14~15MB（预算内）。QPS 量级 ~1/4 于 16T，符合单线程预期；H0 在 1T 亦成立。详见 ndf/evidence/run_poc_measure-512mb-1t-beam32_r032.log + run_trunk_measure-512mb-1t.log |
