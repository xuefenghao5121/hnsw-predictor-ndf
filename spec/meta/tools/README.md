# spec/meta/tools — NDF review harness (not product code)

属 NDF **process profile**（[`../README.md`](../README.md)），与产品 `scripts/` **解耦**。
勿再放到仓库根 `tools/`（该目录已删除；审核 harness 只在本目录）。

**治理全景（逻辑链 / 双表面 / 沙盒契约）先读：**
[`GOVERNANCE.md`](GOVERNANCE.md) — 运行时修图纪律。

**跨 Agent 分发 / Init 先读：**
[`HARNESS.md`](HARNESS.md) — 可移植包入口；实现树在
[`packages/ndf-harness/`](../../../packages/ndf-harness/)。

## 缺陷分类 SoT（先定义，后扫描）

问题空间定义见 process 提案
[`../open/proposal-meta-ndf-defect-taxonomy.md`](../open/proposal-meta-ndf-defect-taxonomy.md)
（Implemented；{#PROP-META-NDF-DEFECT-TAXONOMY}）与 glossary [[DEF-NDF-GRAPH]]…
[[DEF-NDF-BINDER-DUAL-HEAD]]、[[BEH-026]]：Layer A 须同时满足 **NDF 规范锚点** 与
**图论谓词**（DAG/SCC/对称性等）；绑定溯源面（clause↔commit↔binder↔path；曾称 Layer B）另列。
工具只实现已定义的判定，不另造边类型。

## 工具分工

| 脚本 | 职责 |
|------|------|
| [`ndf_index.py`](ndf_index.py) | 条款 **索引 / 检索面**：写 `INDEX.md` + `graph.json`；impact / diff / 轻量 dangling / poc-topics |
| [`ndf_graphcheck.py`](ndf_graphcheck.py) | **图语义面** Linter：环、stable must→非 stable、conflicts 非对称、meta 悬空；错误子图；`--meta` / `--product` |
| [`ndf_advise.py`](ndf_advise.py) | **顾问**：`--surface graph`（图手术单+沙盒）/ `--surface bind`（绑定溯源手术单+虚拟装订器沙盒）；**不**写 SoT |
| [`ndf_advise_bind.py`](ndf_advise_bind.py) | bind 表面实现（由 `ndf_advise` 调用） |
| [`ndf_bindcheck.py`](ndf_bindcheck.py) | **绑定溯源面** Linter：ledger/trailer、装订器双头、观测粒度；DESIGN/INTERFACE 缺席 warning；可选 zombie/drift |
| [`ndf_poc_isolation.py`](ndf_poc_isolation.py) | **POC 写入隔离**（[[BEH-018]] §6）：topic commit / 工作区是否触及 `src/`\|`include/`\|`tests/` |
| [`ndf_perf_baseline.py`](ndf_perf_baseline.py) | **性能线装订**（[[META-007]]）：TOPIC→卡；唯一绑定 `vs`×`config_id`×`measure`；DELTA 缺席 warning |
| [`ndf_close.py`](ndf_close.py) | POC **回合计划面**：往 Trunk 追加清单 + 溯源模板 + post-check（只读 `plan`） |
| [`ndf_workflow_status.py`](ndf_workflow_status.py) | **文字派发 / health / pack**（[[META-009]]…[[META-012]]、[[ADR-META-004]]）：`poc-dispatch`、control/project packs、topic/spec-health；Commander/serve 已退役 |
| [`ndf_poc_dispatch.py`](ndf_poc_dispatch.py) | **POC 派发安全内核**（[[ADR-META-004]]）：硬门、内联租约、最小 completion 校验 |
| [`ndf_context.py`](ndf_context.py) | **Context Compiler**（[[META-012]]）：Task Manifest → role plan → expand/verify；Idea 平面写根分流 |
| [`ndf_replay.py`](ndf_replay.py) | **Deprecated CLI**（[[ADR-META-004]]）：exit 2. Library only for archaeology；日常不写 Episode |

日常：见 [`GOVERNANCE.md`](GOVERNANCE.md) §2 主链。
`graphcheck` → `advise --surface graph`；`bindcheck` → `advise --surface bind`；收口用 `close`。
**Meta 门禁**：`graphcheck --meta`（见上节）。

默认扫描 `spec/meta/` + `spec/00–50`；默认排除 `spec/open/`、`spec/meta/open/`、`spec/archive/`（`--open` / `--archive`）。

**Meta 自洽门禁**（只扫 process-profile 顶点）：

```bash
python3 spec/meta/tools/ndf_index.py index --meta      # → spec/meta/INDEX.md + graph.json
python3 spec/meta/tools/ndf_index.py validate --meta
python3 spec/meta/tools/ndf_graphcheck.py --meta       # MUST hard_errors: 0
python3 spec/meta/tools/ndf_advise.py plan --meta
```

`--meta`：仅 `meta/` 或 `scope=ndf-process`；跨域 ndf 边在 meta 子图上呈悬空硬错误。
`ndf_bindcheck` / `ndf_close` **不加** `--meta`（装订/回合属 POC 面）。

提案：[`../open/proposal-meta-ndf-graph-advise.md`](../open/proposal-meta-ndf-graph-advise.md)、[`../open/proposal-meta-ndf-bind-advise.md`](../open/proposal-meta-ndf-bind-advise.md)、[`../open/proposal-meta-ndf-bindcheck.md`](../open/proposal-meta-ndf-bindcheck.md)、[`../open/proposal-meta-deproductize-clauses.md`](../open/proposal-meta-deproductize-clauses.md)。

## 索引（检索）

```bash
python3 spec/meta/tools/ndf_index.py index
python3 spec/meta/tools/ndf_index.py impact BEH-018
python3 spec/meta/tools/ndf_index.py diff HEAD~1
python3 spec/meta/tools/ndf_index.py validate
python3 spec/meta/tools/ndf_index.py poc-topics
```

生成物：`spec/INDEX.md`、`spec/graph.json`（**不是** NDF must 正文）。

## 图逻辑检查（错误 + 子图）

```bash
python3 spec/meta/tools/ndf_graphcheck.py
python3 spec/meta/tools/ndf_graphcheck.py --format text --hop 2
python3 spec/meta/tools/ndf_graphcheck.py --report tmp/ndf-graphcheck.md
python3 spec/meta/tools/ndf_graphcheck.py --report -          # stdout only
python3 spec/meta/tools/ndf_graphcheck.py --detail            # appendix hop subgraphs
```

默认 `--report tmp/ndf-graphcheck.md`（仓库根 `tmp/`，已 gitignore）。
**MUST NOT** 写入 `spec/open/` 或其它 `spec/` 路径（工具会 exit 2）。OS `/tmp/...` 可用。
报告结构：Summary 表 → Issue index 表 → 按 kind 一张聚合图；`--detail` 才展开逐条子图。

硬错误（exit 1）：`cycle`、`stable_dep`、`conflict_asym`、`meta_dangling`（对齐 taxonomy Layer A）。
Warning（不单独失败）：`unlinked` 孤儿节点。

全文 wiki 断链仍以 `ndf_index.py validate` 为主；`graphcheck` 只检查 **meta 边** 悬空目标。

## 图顾问（advise — 手术单 + 沙盒）

把 graphcheck 问题变成带 Impact_Delta 的 RefactorOptions；`simulate` 只改内存拷贝。

```bash
python3 spec/meta/tools/ndf_advise.py plan --surface graph --low-hanging-fruit --report tmp/ndf-advise.md
python3 spec/meta/tools/ndf_advise.py plan --kinds stable_dep --max-issues 10
python3 spec/meta/tools/ndf_advise.py simulate --surface graph --issue stable_dep-001 --option O1 \
  --report tmp/ndf-advise-sim.md

# v2 绑定溯源面
python3 spec/meta/tools/ndf_advise.py plan --surface bind --low-hanging-fruit \
  --report tmp/ndf-advise-bind.md
python3 spec/meta/tools/ndf_advise.py simulate --surface bind --issue dual-001 --option O1 \
  --report tmp/ndf-advise-bind-sim.md
```

选项按 **confidence → Impact_Delta** 排序。图面默认 `--hop 0`；绑定面沙盒只改内存中的 TOPIC/COMMITS，**永不**写盘或改 git。
提案：[`../open/proposal-meta-ndf-graph-advise.md`](../open/proposal-meta-ndf-graph-advise.md)、[`../open/proposal-meta-ndf-bind-advise.md`](../open/proposal-meta-ndf-bind-advise.md)。

## 绑定溯源检查（bindcheck）

查什么：`Topic:`/`Clauses:` trailer、COMMITS ledger、TOPIC↔Trunk `status` 双头、观测粒度；
装订器设计面（`DESIGN.md` / `INTERFACE.md` 缺席 → warning，不 exit 1）；
可选路径僵尸与时间线漂移。

```bash
python3 spec/meta/tools/ndf_bindcheck.py check --topic l4-cache-mgmt
python3 spec/meta/tools/ndf_bindcheck.py check --all-topics \
  --checks bind,dual,grain,zombie,drift --report tmp/ndf-bindcheck.md
python3 spec/meta/tools/ndf_bindcheck.py check --all-topics --report -
python3 spec/meta/tools/ndf_bindcheck.py check --all-topics --detail
```

默认 `--checks bind,dual,grain`；默认 `--report tmp/ndf-bindcheck.md`。
**MUST NOT** 写入 `spec/`（含 `open/`）。硬错误（exit 1）：`REPRO-BIND-GAP`、`BINDER-DUAL-HEAD`。
`zombie` / `drift` 为 v1 启发式警告（报告标明非图论 / 需人工）。

历史缺 trailer：优先在 `COMMITS.md` **登记 SHA**（不 rewrite git）；已入账的 SHA
**不再**报 `missing_trailer` 硬错。仍可用 banner（豁免 `clause_unbound`）与 `--since` 收窄窗口。

报告风格对齐 `ndf_graphcheck`：Summary 表 → Issue index 表 → 按 topic 聚合图；
ledger 二部图在 Appendix；`--detail` 才展开逐条 evidence/fix。

## POC 写入隔离（scheme A）

对齐 [[BEH-018]] 第 6 条：poc track MUST NOT 写 Trunk `src/` / `include/` / `tests/`；
改头/源先拷进 `poc/<topic>/`。开题/委派前后 SHOULD 跑：

```bash
python3 spec/meta/tools/ndf_poc_isolation.py check --topic l4-cache-mgmt
python3 spec/meta/tools/ndf_poc_isolation.py check --all-topics --workspace \
  --report tmp/ndf-poc-isolation.md
```

硬错误（exit 1）：topic 相关 commit 同时改了禁写路径，或 `--workspace` 下工作区脏了
`src|include|tests`。默认报告 `tmp/ndf-poc-isolation.md`（禁写 `spec/`）。

## 性能线装订（perf baseline）

对齐 [[META-007]] / [[BEH-025]]：解析 TOPIC → `PERF_BASELINE.md` 金标唯一绑定
（`vs` × `config_id` × `measure`）与 Config/Numbers/**Measure**；检查 `DELTA.md` 是否存在。
产品数字/配置快照仍在 `spec/50-verification/{configs,baselines}/`；本工具只做装订校验。

```bash
python3 spec/meta/tools/ndf_perf_baseline.py show --topic <topic>
python3 spec/meta/tools/ndf_perf_baseline.py check --topic <topic>
python3 spec/meta/tools/ndf_perf_baseline.py check --all-exploring
```

硬错误：缺卡/缺 Config·Numbers、缺或不可解析 `vs`/`config_id`、TOPIC sha 与卡 `trunk_sha` 不一致、
`measure_script` 路径不存在。
警告：缺 `## Measure` / `measure_script`、缺 `DELTA.md`、绑定阶段缺 `trunk_sha`（Numbers pending R0）。

## POC 回合计划（close plan）

主题结束（promote / reject / partial）时，**先**生成回合计划，再人工改 Trunk 图；计划强调：

1. 只向 Trunk 既有图 **添加/升格** 节点与边（不复制 `poc/*/ndf` 迷你 SoT）
2. 并入散文必须带 `source:` POC 溯源行
3. 落地后 **MUST** 跑 `ndf_index index` + `ndf_graphcheck`

```bash
python3 spec/meta/tools/ndf_close.py plan --topic l4-cache-mgmt --mode partial
python3 spec/meta/tools/ndf_close.py plan --topic io-pipelining --mode promote \
  --report tmp/close-io-pipelining.md
python3 spec/meta/tools/ndf_close.py plan --topic pq-quality --mode reject
```

`--ids BEH-024 API-012` 可在 `partial`/`promote` 下显式点名回合子集。
`promote`/`partial` plan 含 **§4b Semantic core decision**（[[META-004]]）；`reject` 为 N/A。
第一版 **无** `apply`（不改 SoT / 不自动归档；亦不自动生成 `models/`）。

流程条款正文在 `spec/meta/`；产品行为在 `00–50`。

## Workflow status（文字优先；Commander 已退役）

[[ADR-META-004]]：无 Commander UI、无 ActionSpec、无 `--serve` HTTP。日常入口是
`.cursor/skills/ndf-workflow/`。下列子命令仍可用：

```bash
python3 spec/meta/tools/ndf_workflow_status.py genesis-status --json
python3 spec/meta/tools/ndf_workflow_status.py host-pids --json
python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic <topic> --json
python3 spec/meta/tools/ndf_workflow_status.py spec-health --json
python3 spec/meta/tools/ndf_workflow_status.py poc-dispatch \
  --topic <topic> --intent implement|measure --send
python3 spec/meta/tools/ndf_workflow_status.py pack \
  --topic <topic> --json
python3 spec/meta/tools/ndf_workflow_status.py repair-pack \
  --topic <topic> --task poc_isolation_repair --json
python3 spec/meta/tools/ndf_workflow_status.py control-pack \
  --topic <topic> --task legacy_gate_audit --json
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack \
  --task ndf_improvement_proposal --origin health_finding --json
python3 spec/meta/tools/ndf_workflow_status.py dispatch-send \
  --pack-file tmp/ndf-dispatch-last-pack.json --json
python3 spec/meta/tools/ndf_workflow_status.py lease-record \
  --file tmp/lease.json --json
python3 spec/meta/tools/ndf_workflow_status.py close-plan \
  --topic <topic> --mode promote --json
```

**已退役**（调用则 stderr + exit 2）：`snapshot --serve`、`action-begin` /
`action-finish`、`action-commit`、`capability-approve`、嵌入 Canvas /
`ndf_actions` ActionSpec 目录。历史 `.ndf/replay/` 只读考古；`ndf_replay.py` CLI
另案退役。

Context Compiler 与 close plan 仍独立可用：

```bash
python3 spec/meta/tools/ndf_context.py manifest-create \
  --task poc_implementation --track poc --topic <topic> \
  --report tmp/task-manifest.json --json
python3 spec/meta/tools/ndf_context.py role-plan \
  --manifest <manifest-sha-or-file> --role claude-code \
  --report tmp/context-plan.json --json
python3 spec/meta/tools/ndf_close.py plan --topic <topic> --mode promote
```

Legacy long command block (Commander / Replay / action-*) removed from this README.
For archaeology see `spec/meta/decisions/adr-meta-control-retirement.md`.

保留说明（文字优先）：

- `genesis-status`：`uninitialized` / Foundation / `operational` / `operational_legacy`
- `topic-health` / `spec-health`：只读 finding；报告仅写 `tmp/ndf-workflow-health/`
- `poc-dispatch` / `pack` / `repair-pack` / `control-pack` / `project-control-pack` /
  `dispatch-send` / `lease-record`：文字派发路径（[[ADR-META-004]]）
- `close-plan`：包装 `ndf_close plan`（只读）
- `host-pids`：宿主 PID 卫生诊断（[[META-011]]）

`ndf_actions.py`、`spec/meta/cockpit/`、Commander HTML、ActionSpec registry、
`snapshot --serve`、Canvas skill **已删除/退役**。`ndf_replay.py` 与 `.ndf/replay/`
历史数据本任务不删。

新主题门禁模板：`../templates/poc/GATES.md.stub`；Genesis 模板：
`../templates/genesis/`。文件存在不得推导审批，历史 POC 显示 `legacy_unknown`。
