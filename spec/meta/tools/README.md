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
| [`ndf_workflow_status.py`](ndf_workflow_status.py) | **Workflow/Canvas 派生投影**（[[META-009]]…[[META-015]]）：Genesis、正交 topic 状态、manifest/pack、Replay 摘要、只读 close-plan |
| [`ndf_context.py`](ndf_context.py) | **Context Compiler**（[[META-012]] / [[META-013]]）：Task Manifest → role plan → expand/verify |
| [`ndf_replay.py`](ndf_replay.py) | **Agent Episode Replay**（[[META-013]] / [[META-015]]）：内容寻址 object/event/commit/ref/tag/branch/merge/checkpoint、R0/R1/R2/R3、`guest-run` / guest-proof、`fsck` |

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

## Workflow Canvas / Project Genesis

snapshot / pack / probe 只读树、图、git、装订器与 gateway health，不批准门禁、不启动
Agent、不写 `.openclaw/state.json`。只有 `action-begin` / `action-finish` 会向 gitignored
`tmp/ndf-workflow-actions.jsonl` 追加本地运行审计回执：

```bash
python3 spec/meta/tools/ndf_workflow_status.py genesis-status --json
python3 spec/meta/tools/ndf_workflow_status.py genesis-pack --mode greenfield --json
python3 spec/meta/tools/ndf_workflow_status.py snapshot --json
python3 spec/meta/tools/ndf_workflow_status.py snapshot \
  --format canvas-json --out tmp/ndf-canvas-snapshot.json --json
python3 spec/meta/tools/ndf_workflow_status.py snapshot --serve --topic <topic>
python3 spec/meta/tools/ndf_workflow_status.py snapshot \
  --format canvas-json --json
python3 spec/meta/tools/ndf_replay.py canvas-index --json
python3 spec/meta/tools/ndf_replay.py canvas-ledger --episode <id> --json
python3 spec/meta/tools/ndf_workflow_status.py snapshot --topic <topic> --json
python3 spec/meta/tools/ndf_workflow_status.py snapshot \
  --verify-embedded /absolute/path/to/ndf-workflow.canvas.tsx --json
python3 spec/meta/tools/ndf_workflow_status.py snapshot \
  --update-embedded /absolute/path/to/ndf-workflow.canvas.tsx --json
python3 spec/meta/tools/ndf_workflow_status.py snapshot \
  --update-embedded /absolute/path/to/ndf-workflow.canvas.tsx \
  --replay-episode <id> --json
python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic <topic> --json
python3 spec/meta/tools/ndf_workflow_status.py spec-health --json
python3 spec/meta/tools/ndf_replay.py episode-init \
  --topic <topic> --task poc_implementation --role claude-code \
  --track poc --episode <episode-id>
python3 spec/meta/tools/ndf_context.py manifest-create \
  --task poc_implementation --track poc --topic <topic> \
  --episode <episode-id> --report tmp/task-manifest.json --json
python3 spec/meta/tools/ndf_context.py role-plan \
  --manifest <manifest-object-sha-or-file> --role claude-code --episode <episode-id> \
  --report tmp/context-plan.json --json
python3 spec/meta/tools/ndf_context.py context-expand \
  --plan tmp/context-plan.json --format markdown --report tmp/context-bundle.md
python3 spec/meta/tools/ndf_context.py context-verify \
  --manifest tmp/task-manifest.json --plan tmp/context-plan.json --strict --json
python3 spec/meta/tools/ndf_workflow_status.py action-begin \
  --operation <operation> [--topic <topic>] --json
python3 spec/meta/tools/ndf_workflow_status.py action-finish \
  --action-id <id> --result success|failed [--blocker <reason>] --json
python3 spec/meta/tools/ndf_workflow_status.py pack \
  --topic <topic> --episode <episode-id> --json
python3 spec/meta/tools/ndf_workflow_status.py repair-pack \
  --topic <topic> --task poc_isolation_repair --json
python3 spec/meta/tools/ndf_workflow_status.py control-pack \
  --topic <topic> --task legacy_gate_audit --json
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack \
  --task ndf_improvement_proposal --origin health_finding \
  --episode <episode-id> --json
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack \
  --task ndf_improvement_proposal --origin human_intent \
  --intent-file tmp/ndf-process-intent-<action-id>.md \
  --episode <episode-id> --json
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack \
  --task ndf_improvement_land --proposal spec/meta/open/proposal-meta-<id>.md \
  --episode <episode-id> --json
python3 spec/meta/tools/ndf_workflow_status.py close-plan \
  --topic <topic> --mode promote --json
python3 spec/meta/tools/ndf_workflow_status.py lease-record \
  --file tmp/lease.json --episode <episode-id> --json
python3 spec/meta/tools/ndf_workflow_status.py message-record \
  --file tmp/openclaw-message.json --episode <episode-id> \
  --role openclaw --direction request --coverage messages_only --json
python3 spec/meta/tools/ndf_workflow_status.py completion-record \
  --file tmp/completion.json --episode <episode-id> \
  --role claude-code --coverage completion_only --json
python3 spec/meta/tools/ndf_workflow_status.py close-receipt-verify \
  --receipt tmp/ndf-close-evidence/<topic>/<mode>/<step>.json --json
python3 spec/meta/tools/ndf_replay.py record \
  --episode <episode-id> --kind tool.result --payload tmp/cassette.json --task <task>
python3 spec/meta/tools/ndf_replay.py commit \
  --episode <episode-id> --message "verified completion"
python3 spec/meta/tools/ndf_replay.py audit --commit <sha> --strict
python3 spec/meta/tools/ndf_replay.py reconstruct --commit <sha> --level R1
python3 spec/meta/tools/ndf_replay.py guest-run \
  --commit <sha> --episode <episode-id> --adapter cube
python3 spec/meta/tools/ndf_replay.py guest-run \
  --commit <sha> --episode <episode-id> --adapter vm
python3 spec/meta/tools/ndf_replay.py sandbox \
  --commit <sha> --episode <episode-id> \
  --profile tmp/ndf-replay-sandbox-profile.json --execute
python3 spec/meta/tools/ndf_replay.py fork --from <sha> --branch <name>
python3 spec/meta/tools/ndf_replay.py gate-tag \
  --name <topic/gate> --target <commit> --receipt tmp/gate-receipt.json
python3 spec/meta/tools/ndf_replay.py ledger --episode <episode-id> --write
python3 spec/meta/tools/ndf_replay.py retention-plan
python3 spec/meta/tools/ndf_replay.py fsck
```

- `genesis-status`：`uninitialized` / Foundation / `operational`；既有健康棕地显示
  `operational_legacy`。
- `snapshot`（schema v2）严格分三平面：
  - `business`：本地产品 identity/goals/capabilities/Golden/roadmap/product proposals/topics/risks；
  - `control`：Genesis（含 `accepted` / `genesis_trunk_sha` / `install_needed`）/`kernel_map`（`spec/meta/graph.json` 种子条款）/process proposals/spec health（含 `next_actions`）/gate summary + 保守的 `close` 投影；
  - `runtime`：`implementation`（Claude Code）与 `control`（OpenClaw session_key）双 agent。
  Topic detail 仍正交输出 lifecycle/gates/Design-Implementation-Test/agent_run/health。
  有产品 Charter 时 Canvas 默认 Product；无 Charter 时默认 NDF Control（Genesis 安装轨）。
  `operational_legacy` 只在 Control 显示可选 adopt，不阻断 Product/Topics。
  `snapshot --topic <t>`：单 topic 刷新（Canvas **Refresh topic snapshot**）；返回
  `selected_topic` + 完整 `topics_detail` 供 Topics 工作台更新。
  提案平面按落点目录分类：`spec/open/` → `business.product_proposals`；
  `spec/meta/open/proposal-meta-*.md` → `control.process_proposals`。`track` 头不得
  跨平面改分类；路径/track 不一致写入 `control.spec_health.proposal_plane_warnings`。
  `control.close`：从 binder/NOTES/proposal/tmp tool report 推导 Close Console 步骤；
  未知 graph/build/perf/golden MUST 保持 unknown/pending。`dispatched` 不算完成。
  Canvas payload 另含 `payloadSha`、`absorbedActionId` 与绑定后的 action 摘要；
  `projection_freshness` 为
  `fresh|refresh_in_progress|stale_after_action|unknown`。仅 `fresh` 且 verifier
  `passed + current` 可启用 repair/delegate/close。
  `--format canvas-json` 输出官方 camelCase commander payload（含 `enabledActions`），
  `--out` 写 `tmp/ndf-canvas-snapshot.json`。`--serve` 绑定 `127.0.0.1` 提供 React+D3
  指挥舱与 `/snapshot.json`（Cloud Agent 无入站，不能当云端 URL）；POST `/api/action`
  只接受登记动作。`--update-embedded` 只把 launcher（freshness + Open NDF commander）
  写入 `.canvas.tsx`，完整五页不嵌进 TSX；云端预览读 gzip artifact，须再 Write Canvas
  才会刷新。
  `--probe-runtime` 只读探测 OpenClaw `health --json` **和** Claude ACP
  （`claude doctor` + 配置会话 resume 产物）；只用于页头 Refresh snapshot。例行
  `--update-embedded` 不得带探针。Commander Replay 只嵌 hop 目录 + `replay.focused`
  一页，账本真值在 `.ndf/replay`。Claude CLI 存在不等于
  ACP pipeline/run 可用。`pack` / `repair-pack` / `genesis-pack` 生成时 MUST 探测 ACP，
  并把 `safe_to_delegate`（静态预检）与 `safe_to_dispatch`（静态+运行时）分开。
- `action-begin` / `action-finish`：append-only 本地 action receipt。终态含 repo SHA、
  snapshot SHA、result 与 blockers，并使用统一 receipt 字段和哈希链；断链使投影
  freshness=`unknown`。embedded snapshot verify 另写 payload/absorbed-action receipt。
- `topic-health`：结构化 gate/perf/isolation/bind/preflight finding，并输出
  `space`、evidence、repair owner/task、允许写根与人工口令。报告仅写
  `tmp/ndf-workflow-health/`。
- `spec-health`：项目级 meta/product graph、index validate、all-topic bind 与
  proposal hygiene。无 exploring/blocked POC 时 `binder_health` 为 `not_applicable`
 （Trunk，不跑 `--all-topics`）。Advisor 只读，不自动修 SoT。
- `pack` / `genesis-pack`（pack v2）：Claude Code 实现委派；MUST 含
  `context_plan` / `context_verify` / `static_preflight_passed` /
  `runtime_dispatch_ready`、`workspace.repo_root` 与
  `state_path`；worktree MUST 在 repo_root 下；POC pack 还要求完整 perf 与 isolation
  preflight；委派前先 context-verify，再完成 run/session/base/repo/worktree/branch/
  allowed-root 握手并记录同 topic lease；缺任一条件 `safe_to_dispatch=false`（exit 1）。
- `ndf_context manifest-create|role-plan|context-expand|context-verify`：[[META-012]]
  统一上下文编译。Canvas、OpenClaw、Claude Code 使用不同 role plan，但 MUST 引用
  同一 manifest SHA；参数可使用 Replay object SHA；显式 `--episode` 保存 manifest、
  role plan、bundle、编译后 visible prompt surface 与 verify event。默认 bundle 不含 POC Numbers。
- `ndf_replay`：[[META-013]] 本地内容寻址 Episode。R0 为精确审计，R1 只重建记录
  observation，R2 只执行同一 run/manifest/plan/repo 绑定的 `sandbox` cassette；
  预期输出 MUST 来自该 run 的 completion 或已记录 epsilon expectation，且完整覆盖
  recorded outputs。执行 adapter 为 `bwrap` 或 `vm`；写根不得超出 Context Plan 与
  runtime lease，并要求 network/filesystem/process 隔离与成本/副作用确认。Canvas
  主路径回放是 `guest-run`（`ndf-replay-guest-proof/v1`）。本机 Lvm：`guest-probe`
  看缺口，`guest-image` 预制 Alpine 根文件系统，再 `--adapter vm`。安装步骤见
  `.cursor/skills/ndf-replay-sandbox/`。Cube/E2B 仍可用 `--adapter cube`（proof 记
  `hypervisor_backend=cube`，合同仍是 `adapter=vm`）。禁止 host-mount 现仓；无
  KVM/无镜像/无 Cube 时 `environment_blocked`，不得退回宿主 Composer 执行回放体。R3 总是创建新的
  counterfactual commit/branch。对象使用 AES-256-GCM 本地加密，share-safe export
  创建独立 redacted lineage。重新调用模型不是历史 replay。
- `repair-pack`：Claude Code 有界修复；isolation 只允许写 `poc/<topic>/`，git
  disposition 需人工；measurement 仍要求实现 gate + perf bind。`safe_to_delegate`
  只表示静态预检通过；`runtime_unavailable` 时只准备 ACP lease，不得当作静态失败。
- `control-pack`：OpenClaw Control 委派；MUST 含 `workspace`；OpenClaw 写入
  `{repo_root}/.openclaw/state.json`。Per-repo state 与 gateway session 分离。
  模板见 `spec/meta/templates/openclaw/state.json.example`。
- `project-control-pack`：NDF process 提案。`ndf_improvement_proposal` 写根为
  `spec/meta/open/`，停止于 Pending confirmation，不得改 stable meta 正文或
  `.openclaw/state.json`。`ndf_improvement_land` 在「已确认」后写根覆盖
  `spec/meta/`（含 `open/`）；「已审核」只改该提案头。`origin=health_finding` 要求 current spec-health finding；
  `origin=human_intent` 从仓库 `tmp/` intent artifact 读取非空用户意图并绑定
  `intent_sha`，不要求 finding。两路均要求显式 Episode、Context verify 和实际
  OpenClaw request/response 回执。
- `close-plan`：包装 `ndf_close plan` 为 JSON；仍然只读，无 apply。旧
  `tmp/close-plan-*` 仅显示 `legacy_unbound`；完成 Close step 必须生成并验证
  `ndf-close-evidence/v1` receipt。
- `lease-record`：只向 gitignored `tmp/ndf-workflow-leases.jsonl` 追加已验证 runtime
  lease；必须绑定 Episode 内 exact dispatch pack SHA（`safe_to_dispatch` 或静态预检
  已通过的 lease-prep pack）、`repo_root`、独立 git worktree、
  branch/base 与 allowed root，并写 `acp.start`、lease event、run commit 与
  `refs/runs/<run-id>`；release 必须承接同绑定 active，终态 run id 不得复活；
  同 topic active lease 阻止新写 run。
- `message-record`：捕获 OpenClaw/Claude 可见 request/response；session key 只进加密
  provenance；不完整平台流明确标 `messages_only|completion_only`。
- `completion-record`：将 OpenClaw/Claude completion 与历史 pack 的 manifest/role
  plan/base/write-root、changed-file SHA、git commit、evidence bundle 与 post-check
  receipts 绑定，记录 Episode event + commit；平台无完整流时必须声明
  `completion_only|messages_only`。
- `close-receipt-record|close-receipt-verify`：记录/验证绑定 topic/mode/step/HEAD/
  generation/context/evidence SHA 的 Close receipt。裸 `tmp` 报告不能使步骤变绿。

所有能使 projection、Agent 或 Close 变绿的 receipt MUST 按 [[META-012]] 绑定：

```text
schema | task | topic | mode | step | repo_head | source_generation_sha
manifest_sha | context_plan_sha | command | input_sha | output_sha | evidence_paths
started_at | finished_at | result | blockers
```

旧短回执、NOTES-only、裸 `tmp` 报告显示 `legacy_unbound|unknown`；缺失显示 `missing`。

新主题门禁模板：`../templates/poc/GATES.md.stub`；Genesis 模板：
`../templates/genesis/`。文件存在不得推导审批，历史 POC 显示 `legacy_unknown`。
