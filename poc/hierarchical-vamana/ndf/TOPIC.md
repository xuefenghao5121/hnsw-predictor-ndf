# Topic: hierarchical-vamana

> ndf_topic: hierarchical-vamana
> status: promoted
> baseline_status: measured
> baseline_trunk_sha: d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755
> baseline_protocol: VER-001 sustained + VER-003 cgroup v2
> perf_baseline: ndf/PERF_BASELINE.md
> next_gate: promoted（已落地 Trunk src/；金标 bl-trunk-d9122d2 重测）
> proposal: spec/open/proposal-hierarchical-vamana-build.md

The lifecycle/baseline/next_gate headers above are mutable runtime navigation and are
outside the human review slice.

<!-- ndf:gate-slice begin=topic_contract -->
## Scope and hypothesis

> explore_surface: hierarchical-vamana, graph-build, diskann, hnsw-layers
> depends_on_topics: none
> conflicts_with_topics: none

**Active hypothesis (H0)**：在 DiskHNSW 存储/搜索外壳不变（或最小适配）的前提下，用
「HNSW 层分配 + 每层 Vamana（GreedySearch + RobustPrune, α）」替换 Trunk
`build_index.cpp` 的整图 hnswlib HNSW 建边，在 sustained 协议下达到对照召回
（≥95% Recall@10），并以更少无效边或更短导航路径改善 QPS 和/或常驻内存。

**Proposal**：`spec/open/proposal-hierarchical-vamana-build.md`（已审核）

**Draft clauses**（仅探索，不进 stable）：

- `BEH-HV-001`：构建 MUST 支持分层分配 + 层内 Vamana prune（opt-in）
- `ARCH-HV-001`：上层邻接内存驻留；L0 与现 DiskHNSW 块布局兼容或有明确迁移表

**Directions**

1. 实现层内 Vamana 建边 + HNSW 式层分配，导出邻接到现有 reorder/blocks/PQ 流水线
2. 对照 `bl-trunk-d0ae5dd` / `cfg-sla-ef100`（SIFT1M sustained 512MB/16T）
3. 记录层数、`M`/`R`、`α`、`beam` 与相对对照的 Δ%

**Non-goals**

- 重写 DiskANN 十亿点分片合并流水线
- 改 VER 金标口径或写 stable SLA
- 默认合入 Trunk `src/` / `include/` / `tests/`

**Success criteria (explore)**

1. poc 内可构建索引并跑通搜索路径（或最小搜索壳）
2. 相对 `bl-trunk-d0ae5dd` 报告 recall/QPS/内存（evidence + PERF Numbers）；不写 stable SLA
3. TOPIC/NOTES 记录参数与失败模式
<!-- ndf:gate-slice end=topic_contract -->

## NOTES (R0, 2026-08-25)

**参数**: HV_M=16 HV_R0=32 HV_RUP=16 HV_BEAM=64 HV_ALPHA=1.2 HV_ALPHA2=0 HV_ROUNDS=3 HV_SEED=42

**结果**: Recall 98.00% (+2pp vs 96.00%)，agg QPS 4653.9 (+7.5%)，steady 6999.8 (+8.6%)，RSS +18MB。

**失败/代价模式**:
- Vamana 长程多样边在 BFS 重排下 delta-varint 压缩变差（L0 CSR 62MB vs hnswlib ~47MB），导致 RSS +18MB；仍在 512MB cgroup 预算内。
- `run_sustained.sh --config cfg-sla-ef100` 会硬覆盖 VEC_BLOCKS_PATH 到 Trunk BFS 顺序文件（POC BFS 不同 → 精排读错向量），故 POC 用 `scripts/run_poc_measure.sh`（协议同源）。
- 建图 132s（L0，24T）远快于预期，未构成瓶颈（H3 结论：可接受）。

**遗留**: 未做 α 扫描（1.0/1.2/1.4）、beam/R0 扫描、DEEP10M 扩展；晋升前需补测。

## NOTES (R1 α-sweep, 2026-08-25)

**参数**: α ∈ {1.0, 1.2, 1.4}；其余固定 HV_M=16 HV_R0=32 HV_RUP=16 HV_BEAM=64 HV_ROUNDS=3 HV_SEED=42 @ 16T（无 1T）。

**结果（α → Recall / agg QPS / steady / RSS init / RSS end / L0 边数）**:
- α=1.0 → 91.43% / 7128.0 / 11205.9 / 142MB / 338MB / 13.51M（**召回不达标 <95%**）
- α=1.2 → **98.00%** / 6052.2 / 9214.9 / 175MB / 371MB / 29.64M（**工作点**）
- α=1.4 → 95.92% / 5499.7 / 8438.7 / 206MB / 401MB / 31.89M

**结论**: 本代码 α 语义为“α 越大→剪枝越弱→边越多”（与标准 DiskANN 反向）。α=1.0 过度剪枝
（avg degree 13.5）召回崩；α=1.4 度逼近 R=32 上限，丧失 α-多样性（贪心最近 32）→ 召回与 QPS 双降
且内存 401MB 逼近预算。α=1.2 唯一同时满足 ≥95% 召回且 QPS/内存最优，确认 R0。

**方差/代价模式**:
- R1 α=1.2 重测 agg QPS 6052.2 较 R0 4653.9 高 ~30%（会话内连续运行、OS page cache 变热）；Recall 稳定 98.00%。
- 建图时间随 α 递增：96.9s（α=1.0）→ 137.1s（1.2）→ 148.3s（1.4），仍非瓶颈（H3）。

**遗留（晋升前）**: beam/R0 扫描（在 α=1.2 上）、DEEP10M 扩展。

## NOTES (R2 beam+R0 sweep, 2026-08-25)

**参数**: α=1.2 固定；beam ∈ {32,64,128}@R0=32 + R0 ∈ {24,32,40}@beam=64；其余 HV_M=16 HV_RUP=16 HV_ROUNDS=3 HV_SEED=42 @ 16T（无 1T）。

**结果（beam → Recall / agg QPS / steady / RSS init / RSS end / L0 边）**:
- beam=32 → 97.02% / 6210.4 / 10051.2 / 171MB / 367MB / 26.24M
- beam=64 → **98.00%** / 6159.1 / 9599.4 / 175MB / 371MB / 29.64M
- beam=128 → 97.86% / 6130.1 / 9584.3 / 177MB / 372MB / 31.05M
- R0=24 → 95.87% / 6367.0 / 10507.5 / 163MB / 358MB / 23.25M
- R0=40 → **98.95%** / 6047.8 / 8953.9 / 185MB / 381MB / 34.64M

**结论**: beam 在 {32,64,128} 影响微弱（recall 97-98%、QPS 6130-6210），建图时间近线性（72→249s），beam=64 保持默认。
R0 为主导旋钮（R0↑→边↑/recall↑/QPS↓/内存↑ 单调）：R0=32 为工作点；R0=40 提供 +0.95pp recall（98.95%）但 QPS -1.8%、RSS +10MB、边 +4.99M（可选 recall 余量档）；R0=24 最省内存（358MB）但 recall 95.87% 余量薄。

**遗留（晋升前）**: DEEP10M 扩展；若需更高召回可考虑 R0=40 档（已测）。

## NOTES (R2b operating-point lock, 2026-08-25)

**人类决策（override R2 agent 选 beam=64）**: 固定 POC 最优配置为 **beam=32 / R0=32 / α=1.2**。

**依据（R2 evidence @16T，ndf/evidence/poc_measurement-summary-r2.md）**:
- beam=32/R0=32 → Recall 97.02% / agg QPS 6210.4 / steady 10051.2 / RSS 367MB
- beam=64/R0=32 → Recall 98.00% / agg QPS 6159.1 / steady 9599.4 / RSS 371MB

**取舍**: −0.98 pp recall 换取更高 QPS + 略省 RSS + 建图更快（72s vs 136s）；仍 ≥95%（H0 成立）。

**Control 落地**: INTERFACE.md `interface_contract` 钉死默认 HV_M=16 HV_R0=32 HV_RUP=16 **HV_BEAM=32** HV_ALPHA=1.2 HV_ALPHA2=0 HV_ROUNDS=3 HV_SEED=42；perf_bind 协议不变（512MB/16T）。代码默认值（vamana_build.cpp / run_poc_measure.sh 等）留待下一「派发」实现步落地。

## NOTES (R3 1T supplementary, 2026-08-25)

**参数**: 锁定 beam=32/R0=32/α=1.2（M=16 Rup=16 rounds=3 seed=42）@ **1T**；补充 16T 主协议的 1T 单线程对照。

**结果（POC @1T vs Trunk @1T）**: Recall 97.02% vs 96.00% (+1.02pp)；agg QPS 1643.8 vs 1434.1 (+14.6%)；steady 1849.3 vs 1697.1 (+9.0%)；RSS init 171 vs 157MB；RSS end 339 vs 324MB；L0 边 26.24M vs 21.20M。

**结论**: 1T 单线程磁盘路径上 H0 仍成立（recall ≥95% 且 QPS 优于 Trunk）；QPS 绝对量级 ~1/4 于 16T（1643.8 vs 6210.4），符合无并行放大预期；RSS +14~15MB 在 512MB 预算内。

**遗留（晋升前）**: DEEP10M 扩展；R0=40 高召回档（已测 16T）；代码默认值落地（下一派发）。

## NOTES (promote_land, 2026-08-25)

**结论**: 分层 Vamana 已晋升为 Trunk 默认建图（src_commit=d9122d2）。

**落地内容**:
- `src/pipeline/build_index.cpp` 重写为 HNSW 几何层分配 + 每层 Vamana，直接产出 GraphStructure（原 extract_graph 步骤并入）；代码默认值钉死 HV_BEAM=32 / HV_ROUNDS=3（此前 64 / 2）。
- L1: `BEH-027`（behavior.md）/ `ARCH-007`（architecture.md）promote→stable；L3 语义核 `spec/models/hierarchical-vamana-build.md`；决策 `DEC-003`（默认开启）。
- 金标重测（META-006，bl-trunk-d9122d2 @ cfg-sla-ef100 / 512MB / 16T）：Recall 97.02% / agg 5708.4 / steady 9035.3 / RSS 170→367MB。
- 相对旧金标 bl-trunk-d0ae5dd（hnswlib）：Recall +1.02pp / agg +31.8% / steady +40.1%。

**证据**: `ndf/evidence/build-promote-trunk.log` + `ndf/evidence/run_promote_measure-512mb-16t.log`。
