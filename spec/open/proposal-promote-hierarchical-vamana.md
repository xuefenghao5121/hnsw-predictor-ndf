# 提案：将分层 Vamana（HNSW 层级 × 层内 Vamana）晋升为 Trunk 默认建图

> track: promote
> status: Implemented
> reviewed: 2026-08-25T16:26:12Z
> plane: product
> topic: hierarchical-vamana
> mode: promote
> proposal-id: promote-hierarchical-vamana
> flow-id: promote-hierarchical-vamana
> 日期: 2026-08-25
> prior_poc_proposal: spec/open/proposal-hierarchical-vamana-build.md (reviewed)
> close_plan: tmp/ndf-close-plan-hierarchical-vamana-promote.md
> depends-on: CHR-001, ARCH-001, ARCH-002, CON-SLA-001, VER-001, BEH-001, BEH-002
> Promotes: hierarchical-vamana
> 范围: 将 Trunk 默认整图 hnswlib 建图替换为 HNSW 几何分层 + 每层 Vamana（GreedySearch + RobustPrune）；导出到现有 DiskHNSW reorder/blocks/PQ/搜索外壳

Status: Implemented on 2026-08-25 (human phrase `已确认` at 2026-08-25T16:22:22Z).
L1 draft→stable / L3 model / Trunk `src/` land after `已审核` + Implementation 派发.

<!-- ndf:gate-slice begin=proposal_contract -->

## 1. 背景与对照目标

POC `hierarchical-vamana`（`poc/hierarchical-vamana/`）已完成 R0–R3 探索，H0 假设在
sustained 协议下成立：用「HNSW 层分配 + 每层 Vamana RobustPrune 建边」替换 Trunk 整图
hnswlib HNSW 建边，可达到对照召回（≥95%）并以更少无效边改善 QPS（代价是 delta-varint
压缩变差、RSS 略增，仍在 512MB cgroup 预算内）。

> source: poc/hierarchical-vamana/ndf/TOPIC.md ; poc/hierarchical-vamana/ndf/DELTA.md ; poc/hierarchical-vamana/ndf/PERF_BASELINE.md @ d0ae5dd
> track: promote ; Topic: hierarchical-vamana

本提案（promote）将探索期草案晋升为 Trunk 稳定契约：**默认建图路径**由整图 hnswlib
替换为分层 Vamana，搜索路径 / Fine Rerank / BlockCache / PQ 不变（除非最小适配胶水）。

## 2. 合并范围（已确认方向）

Replace Trunk default **hnswlib whole-graph build** with **HNSW geometric layering +
per-layer Vamana**（GreedySearch + RobustPrune），导出邻接到现有 DiskHNSW
reorder / blocks / PQ / search shell。

> source: tmp/intent-promote-hierarchical-vamana.md ; tmp/ndf-close-plan-hierarchical-vamana-promote.md
> track: promote ; Topic: hierarchical-vamana

- 建图入口 `src/pipeline/build_index.cpp`：整图 hnswlib HNSW → 分层 Vamana。
- 导出邻接（GraphStructure）→ 现有 BFS reorder / write_blocks / gen_route / PQ 流水线复用。
- 搜索：上层纯内存下降 → L0 + 现有 Fine Rerank / BlockCache（不变）。

## 3. 锁定运行默认值（POC 人工 override）

```text
HV_M=16 HV_R0=32 HV_RUP=16 HV_BEAM=32 HV_ALPHA=1.2 HV_ROUNDS=3 HV_SEED=42
```

> source: poc/hierarchical-vamana/ndf/INTERFACE.md ; poc/hierarchical-vamana/ndf/TOPIC.md (NOTES R2b)
> track: promote ; Topic: hierarchical-vamana

- beam=32（人类 override R2 agent 选 beam=64）；α=1.2；R0=32。
- 不晋升 GBDT（`LEARNED_EF`）：R0–R3 全程关闭，非本主题范围。

## 4. 证据（仅引用；非 stable must SLA）

| round | 内容 | 证据路径 |
|-------|------|----------|
| R0 | build+measure vs `bl-trunk-d0ae5dd` @ cfg-sla-ef100 / 512MB/16T | `poc/hierarchical-vamana/ndf/evidence/run_poc_measure-512mb-16t.log` |
| R1 | α sweep {1.0,1.2,1.4} → α=1.2 工作点 | `poc/hierarchical-vamana/ndf/evidence/poc_measurement-summary.md` |
| R2 | beam/R0 sweep；人类锁定 beam=32（vs agent beam=64） | `poc/hierarchical-vamana/ndf/evidence/poc_measurement-summary-r2.md` |
| R3 | 1T 补充 @ 锁定配置 vs Trunk @1T | `poc/hierarchical-vamana/ndf/evidence/run_poc_measure-512mb-1t-beam32_r032.log` + `run_trunk_measure-512mb-1t.log` |

> source: poc/hierarchical-vamana/ndf/PERF_BASELINE.md ; poc/hierarchical-vamana/ndf/DELTA.md
> track: promote ; Topic: hierarchical-vamana

**纪律**：以上数字为 POC draft，**不**复制为 Trunk stable must SLA（[[CON-POC-001]]）。
落地后须按 [[META-006]] 重测并更新金标基线（见 §9）。

## 5. 草案 → 稳定 ID 清单（MUST）

| POC draft | Suggested Trunk | disposition |
|-----------|-----------------|-------------|
| `BEH-HV-001` | `BEH-027`（或下一空闲 BEH） | promote：opt-in 或默认建图 MUST 支持分层 Vamana |
| `ARCH-HV-001` | 下一空闲 ARCH（或扩展 ARCH-001/002） | promote：上层邻接内存驻留；L0 布局与 DiskHNSW 兼容 |

> 实际稳定 ID 在 Implementation 落地时按「next free」规则分配，本表仅记录建议。

另需（视情况）：

- `DEC`：默认开启 vs opt-in 标志位决策（若 Trunk 默认开启需一条 DEC 记录）。
- `VER` / `CON-SLA`：仅在落地后金标基线需要更新时新增（[[META-006]]）——优先重测后更新，
  **不**复制 POC QPS 表作为 must SLA（[[CON-POC-001]]）。

## 6. 语义核（[[META-004]] / §4b）—— 要（蒸馏 L3）

在 promote 提案/落地中交付 L3 oracle：

1. 新增 `spec/models/hierarchical-vamana-build.md`（仅覆盖以下 oracle 内容）：
   - **enable / when to use**：build-time 建图；默认开启或 opt-in（DEC 待定）；搜索路径不变。
   - **timing**：索引构建期（build-time），非 search-time；替换 build_index.cpp 整图 hnswlib。
   - **ops / parameters**：`M=16 R0=32 Rup=16 beam=32 α=1.2 α2=0 rounds=3 seed=42`。
   - **invariants**：层分配与边端点层一致（无指向更高层非法边）；prune 语义（α 越大→剪枝越弱→边越多，与标准 DiskANN 反向）；导出 L0 邻接兼容现有 DiskHNSW 加载。
2. 在 owning L1 条款上打 `model=hierarchical-vamana-build`。
3. **禁止**将 poc 树 / patches / COMMITS / evidence Numbers 复制进 `spec/models/`。

> 模型文件在「已审核」后随 Implementation 一并落地（本 Control hop 仅草拟 outline，
> 不写 `spec/models/`，因当前 writable 仅 `spec/open/`）。

## 7. Trunk 写入面

- `src/pipeline/build_index.cpp`（及相关 helper）
- 文档（`docs/`）如需要
- `Promotes: hierarchical-vamana`

## 8. 非目标

- 不晋升 GBDT（`LEARNED_EF`）。
- 不重写 DiskANN 十亿点分片合并流水线。
- 不重写搜索栈（Fine Rerank / BlockCache / PQ / 图引导预取不变）。
- 本 hop **不落地 Trunk 代码**——停在提案草稿等「已确认」。

## 9. 落地后清单（未执行；供 Implementation 参考）

- [ ] 重测 Trunk 新 `src` SHA 上的 sustained（[[META-006]]），更新金标基线，**不**复制 POC QPS。
- [ ] `python3 spec/meta/tools/ndf_index.py index` + `ndf_graphcheck.py`。
- [ ] 落地 `spec/models/hierarchical-vamana-build.md` 并 wire `model=`。
- [ ] 同步 TOPIC/NOTES/COMMITS/archive 项（[[BEH-025]]）。

<!-- ndf:gate-slice end=proposal_contract -->

## Control receipts

| event | phrase | actor | at | proposal_sha | flow_id | hop | status |
|-------|--------|-------|----|--------------|---------|-----|--------|
| proposal.confirmed | 已确认 | human | 2026-08-25T16:22:22Z | 7f13f790a8a3351418791bfaa524cd59c5dd30f21f35b74127b01255c1ada625 | promote-hierarchical-vamana | confirm_land | approved |
| proposal.reviewed | 已审核 | human | 2026-08-25T16:26:12Z | 7f13f790a8a3351418791bfaa524cd59c5dd30f21f35b74127b01255c1ada625 | promote-hierarchical-vamana | review | approved |
