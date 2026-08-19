# Meta Process — 探索轨 / 晋升 / 负结果 / 装订

> scope: ndf-process  
> 条款索引: `CHR-008`, `BEH-018`, `BEH-019`, `BEH-020`, `BEH-025`, `BEH-026`,
> `META-006`, `META-007`, `META-009`, `META-010`, `META-011`, `META-012`, `META-013`, `META-014`, `META-015`
> 目录边界: [[ARCH-008]]；SLA 隔离: [[CON-POC-001]]  
> 术语: [[DEF-020]], [[DEF-021]], [[DEF-022]], [[DEF-023]], [[DEF-NDF-GRAPH]]  
> 缺陷分类: [[DEF-NDF-CYCLE]]…[[DEF-NDF-BINDER-DUAL-HEAD]]（见 `meta/glossary.md`）

## 探索与晋升双轨 {#CHR-008}
<!-- ndf: kind=arch level=must layer=L0 status=stable since=0.7 source=deduced scope=ndf-process -->

本仓库产品规范与代码演进 MUST 区分：

1. **探索轨（POC）**：验证某优化/机制是否成立；允许失败与回退（[[DEF-020]]）。
2. **主线轨（Trunk）**：已证明有效、纳入产品行为与 SLA 的实现（[[DEF-021]]）。

探索轨产物 MUST NOT 被默认当作 Trunk SoT；负结果 MUST 以决策记录关闭，不得靠
「静默删条款却留主线代码」或「删代码却留 stable must」维持表面一致。

反面教材：探索方向过早合入 Trunk 后证伪（详见产品负结果 DEC）。
流程细则见 [[BEH-018]]…[[BEH-020]]；目录边界见 [[ARCH-008]]。

## 探索期 NDF 纪律 {#BEH-018}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->
<!-- ndf: refines=CHR-008 depends-on=ARCH-008,DEF-020 -->

当某方向仍在探索轨时：

1. 契约草稿 MUST 留在 `spec/open/proposal-*.md` 或主题装订器 `poc/<topic>/ndf/proposals/`，
   或固定目录中显式 `status=draft` / `level=tbd`；凡本主题提案 MUST 登记进
   `poc/<topic>/ndf/TOPIC.md`（[[BEH-025]]）。**流程/卫生**提案 MUST 写在
   `spec/meta/open/proposal-meta-*.md`（见 `AGENTS.md` track=process）。
   Draft 状态的存在与演进 MUST 由 `spec/meta/open/draft-map/` 并发映射承载；
   固定模块正文的 `status` 字段 MUST NOT 单独充当 Draft 事实源。
2. MUST NOT 将探索期指标写入 `status=stable` 的 `{#CON-SLA-*}` must 行
3. MUST NOT 将探索期行为标为生产默认（环境变量默认开启、去掉 opt-in 门控等）
4. 正文与提案 MUST 使用明确标记：`POC` / `status=draft` / `explore=`，并 `depends-on`
   对应开放提案或 DEC 方向
5. 多轮深入（v1→v2→…）MUST 在**同一探索主题**下追加证据，优先改 `poc/<topic>/`、
   装订器与提案，而不是反复改写 Trunk 的 stable 条款
6. **可执行试错 MUST 落在 `poc/<topic>/`**（或专用 POC 分支）。探索期 / poc track：
   **MUST NOT 修改** Trunk 树中的 `src/**`、`include/**`、`tests/**`（含头文件与
   「生产默认路径」）。若 POC 需改接口或实现：MUST 将相关 `.h`/`.cpp`（及必要依赖）
   **复制到** `poc/<topic>/` 后再改；对本 topic 修改面，构建 MUST 优先使用 topic 内
   路径（如 `-I.`），MUST NOT 向 Trunk `include/` / `src/` 写回。**MAY** 只读编译链接
   **未修改**的 Trunk 源/头（例如未改动的 `../../src/core/*.cpp`、`-I../../include`
   中未改动的头）作 R0/对照。若已误改 Trunk：MUST 按 [[BEH-020]] 或显式 revert /
   迁出到 `poc/`，并做矫正检查（见 `AGENTS.md` §6.2a）。开题/委派前后 SHOULD 跑
   `python3 spec/meta/tools/ndf_poc_isolation.py check --topic <topic>`。
7. MUST NOT 在未登记 `TOPIC.md` 的情况下改写 Trunk `status=stable` 条款「顺便服务某 POC」
8. 探索中发现的 Trunk 缺陷（主线 bug）：默认 MUST 在当前 `poc/<topic>/` 登记为 bug
   切片并修测取证（TOPIC / amend 提案 / COMMITS）；MUST NOT 为「顺便修 bug」绕过本条
   第 6 款直接改 Trunk `src/` / `include/` / `tests/`。确认合入时 MUST 开产品提案
   （track=bug 或挂 promote 干净切片），干净合入 `src/`（及必要 `include/`），并可用
   `ndf_close --mode partial` 收口子集而主题继续 exploring。仅当缺陷已确认与当前假设
   无关且需紧急修生产路径时，允许 track=bug 直改 Trunk，事后 MUST 补 DEC/VER。
9. 开题前 MUST 扫描活跃 exploring 主题的 `explore_surface`（[[BEH-025]]）：
   相交则 MUST 串行（`depends_on_topics`）或声明 `conflicts_with_topics`，MUST NOT 默认可并行。

> rationale: 过早把探索写进 Trunk stable，或直接改 `src/`/`include/`，是 NDF 与 Trunk
> 漂移的主因（反面样板见产品负结果 DEC；含误改头文件）。写入隔离（方案 A）：改则必拷
> 进 `poc/<topic>/`，允许只读链未改 Trunk。主题装订器提供收敛与可复现，不引入第二套
> must SoT。POC 内发现主线 bug 见第 8 条；有条件并行见第 9 条与 [[BEH-025]]。
> 提案：`spec/meta/open/proposal-meta-poc-write-isolation.md`。

## 晋升闸门 {#BEH-019}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->
<!-- ndf: refines=CHR-008 depends-on=DEF-021,DEF-022,META-004,META-005 -->

晋升到 Trunk MUST 同时满足：

1. **证据**：至少一组与目标协议一致的测量；MUST 对齐产品树现行诚实基准与严格隔离
   验收协议（权威路径：`spec/40-constraints/sla.md`）
2. **提案**：`proposal-*` 经人工确认；固定目录条款从 draft→stable（或新增 stable）；
   promote 提案 MUST 列出 draft→stable ID 清单，并引用该主题 `TOPIC.md`
3. **代码**：以**干净合入**方式进入 `src/`（重写/cherry-pick 最小切片），
   commit message 引用条款 ID 与提案/DEC，并含 trailers：`Topic:`、`Proposals:`、
   `Clauses:`、`Promotes: <topic>`（[[BEH-025]]）
4. **验证**：触发编译验证与相关 SLA/VER；失败则不得宣称已晋升
5. **装订器最终收口**：在代码集成、index/graphcheck、编译、适用的性能与金标验证全部通过前，
   主题只能处于 `closing` 编排态，MUST NOT 先标 `promoted` 或归档。全部通过后：
   `TOPIC.md` status → `promoted`；`COMMITS.md` 记录 `src_commit` + `spec_commit`；
   装订器迁入 `spec/archive/YYYY-MM/poc-<topic>/` 或保留摘要指针（二选一，promote 提案写明）。
   若存在 `poc/<topic>/NOTES.md`，MUST 将文件头 status 与 TOPIC 对齐为 `promoted`
   （日期/DEC/提案指针；见 [[BEH-025]]）。**partial** 且主题仍 exploring 时：
   NOTES SHOULD 标明 `partial` + TOPIC 仍 exploring，MUST NOT 写成全量关闭。
6. **语义核决策**（[[META-004]]）：promote 或 partial 收口 MUST 决定是否蒸馏 L3 语义核
   （**要** / **不要** / **延期**）。造核为 MAY（同提案或紧随产品提案交付 `spec/models/` +
   `model=`）；MUST NOT 用 poc/patch/ledger 冒充金标；**不**替代 VER。
   决策清单承载面：`python3 spec/meta/tools/ndf_close.py plan --mode promote|partial`
   （只读 plan；缺 MODEL 不是工具失败条件）。
   若合入引入或变更运行时旋钮 / 性能约束，SHOULD 按 [[META-005]] 更新相关条款的
   `trunk-ref=`（指向合入 feat SHA 或 tag）。
7. **基线失效与表面冲突**（[[BEH-025]]）：promote 或 partial 合入后 MUST：
   - 将受影响 exploring 主题（**含本主题若仍 exploring**）`baseline_status` → `stale`；
   - 对 `explore_surface` 相交的活跃主题做冲突/依赖复核（`conflicts_with_topics` /
     `depends_on_topics`）；MUST NOT 默认可加跨主题收益。
   清单承载：`ndf_close` plan §4c / §4d。
8. **Draft 映射受控路径**：晋升 MUST 以 `spec/meta/open/draft-map/` 映射条目为闸门。
   条目 `proposed_status` MUST 按 `exploring → closing` 由提案确认触发；全部闸门通过后
   MUST 将映射条目归档（`spec/meta/open/draft-map/archive/` 或等效摘要指针），然后固定
   模块正文才写入对应 `status=stable` 条款。MUST NOT 在映射条目仍 `exploring` 时把正文
   写成 stable。

禁止：先合主线再补 stable 契约；或先写 stable must 再补 POC 证据。

## 金标更新义务 {#META-006}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.11 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=BEH-019 -->

每次 promote / bug / refactor 合入 Trunk `src/` 后，MUST：

1. 重跑产品树现行 Golden 约束声明的标准配置与测量矩阵。
2. 生成或更新产品验证树中的 Golden Baseline：
   - 绑定新 Trunk SHA（`git rev-parse HEAD`）
   - 记录现行协议要求的性能、质量、稳定性与资源指标
3. 如配置参数变更（新增/修改运行时旋钮、默认值、数据路径），同步更新产品 Golden
   约束所指向的配置快照。
4. 金标更新 commit MUST 引用触发的 promote/bug 提案（`Promotes:` / `Fixes:` trailer）。

**豁免**：纯文档变更（spec/ / README）、POC 目录内变更（poc/）不触发金标更新。

> rationale: 性能测试不仅依赖代码，还依赖配置参数。流程层只规定 SHA + 配置 + 测量结果
> 的更新义务；具体矩阵、路径与指标属于产品验证树。

## POC 性能线唯一绑定 {#META-007}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.12 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=BEH-025,META-006 -->

活跃性能 POC MUST 由 TOPIC `perf_baseline` 唯一指向 `PERF_BASELINE.md`，卡头 MUST 绑定：

```text
vs × config_id × measure_script
```

1. `vs` 标识比较金标或显式 Trunk 基准；`config_id` 标识配置快照；
   `measure_script` 标识可执行测量入口，可另列 `measure_binary`。
2. 首次 R0 前 Numbers MAY 为 pending；R0 后 MUST 写 `baseline_trunk_sha`、
   `baseline_status=current` 与 Numbers。
3. 比 Δ% / 压测 MUST 只读 TOPIC → PERF_BASELINE（绑定与 Numbers）→ DELTA；
   MUST NOT 从 stable SLA 或 NOTES 抄观测数字。
4. `DELTA.md` 记录 Feature / Hotspot / Bind snapshot / Rounds，是 Design↔Test 变化账本，
   不替代比较 SoT 或原始 evidence。
5. 配置-only 变更 MUST 更新绑定并重测，不得以修改 stable SLA 代替。

> rationale: 性能结论必须能回答「对谁、用什么配置、由哪个入口、得到哪些数」；
> SLA 是合约下限，不是探索观测线。

## Project Genesis 初始化轨 {#META-009}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.13 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-003,META-008 -->

NDF 工作流 MUST 在日常 Proposal/POC 前支持一次性 `track=bootstrap`：

```text
> track: bootstrap
> bootstrap_mode: greenfield | adopt
```

- `greenfield` 从用户原始 IDEA 建立项目目标、本地 NDF Foundation 与初始 Trunk candidate。
- `adopt` 对已有代码做 observed 盘点、建立本地 NDF、验证并冻结 Genesis；
  MUST NOT 改写既有 git 历史。
- 已存在 accepted Project Genesis 决策的 operational 项目 MUST NOT 重跑 bootstrap；
  重建基准另走 process/refactor 提案。
- 兼容既有健康棕地：无 Genesis 决策但已有完整 `spec/00–50`、产品代码与可运行治理门禁时，
  工作台 MAY 标 `operational_legacy` 并提示可选 adopt；MUST NOT 因新流程阻断既有日常 POC。
  日常指挥面是 NDF commander；Cursor Canvas 不是持续叠加 topic/hop 的承载。

初始化门禁 MUST 串行：

```text
IDEA已审核 → CHARTER已审核 → ARCHITECTURE已审核
→ VERIFICATION已审核 → 可以建立初始主线 → GENESIS已审核
```

1. 用户原始 IDEA MUST 原样保存来源；确认后的目标/scope/non-goals 进入产品 Charter，
   取舍、已知 draft 与 Genesis 绑定进入产品 Genesis 决策。
2. 无证据的性能数字 MUST 为 draft/TBD/`not-established`，MUST NOT 冒充性能金标。
3. 收到「可以建立初始主线」后才可通过 Claude Code 隔离环境建立最小可构建垂直切片。
4. Claude Code MAY 写初始代码、测试、构建配置与 L2/L3；MUST NOT 修改 L0/L1、
   Charter、Architecture、Decisions 或 `spec/meta/`。
5. NDF 图、构建、最低功能验收与三空间追踪均闭合后，Project Genesis 决策 MUST 绑定
   IDEA 来源、NDF tree SHA、Trunk SHA、verification ref 与 known drafts；
   收到 `GENESIS已审核` 后项目才进入 `operational`。

项目目标金标（Charter + Genesis 决策 + git SHA）与性能 Golden Baseline 是不同对象。

## 人工门禁回执 {#META-010}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.13 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-001,META-008 -->

需要机械展示或自动委派的人工作业 MUST 使用 append-only 门禁回执。POC 回执位于
`poc/<topic>/ndf/GATES.md`；Genesis 使用初始化 GATES。每条回执 MUST 记录：

```text
gate / phrase / approved_by / approved_at
approved_content_sha / source_ref / status
```

1. 文件存在 MUST NOT 推导为人工已审核；缺回执时只能显示 `missing` / `unknown`。
2. 内容 SHA MUST 由该闸绑定的 canonical 文件束计算；实质修改后，下游回执 MUST
   追加 `invalidated`，不得改写历史审批。
3. POC 的 `topic_review` 绑定 TOPIC + root proposal；
   `design_review` 绑定 TOPIC + DESIGN；
   `implementation_approval` 绑定 TOPIC + DESIGN + PERF_BASELINE 绑定头 + DELTA 假设 +
   INTERFACE。
4. 口令仍由人触发；Canvas/Agent MUST NOT 静默批准或伪造 `approved_by`。
5. 本条不要求回填历史 POC；历史主题显示 `legacy/unknown`。

### POC 门禁 review slice

新建或已迁移主题的门禁 MUST 绑定显式 `review_slice`，而不是冻结整份探索日志。
切片标记 MUST 在同一文件内成对、ID 唯一、不可嵌套；canonical 输入为：

```text
slice_id NUL repo_relative_path NUL slice_bytes NUL
```

bundle 中切片按 `slice_id + path` 排序后计算 SHA-256。推荐标记：

```markdown
<!-- ndf:gate-slice begin=topic_contract -->
... reviewed contract ...
<!-- ndf:gate-slice end=topic_contract -->
```

| gate | review slices |
|------|---------------|
| `topic_review` | TOPIC intent/scope/hypothesis/directions/proposal contract |
| `design_review` | topic contract + DESIGN goals/non-goals/modules/data-flow/trunk-boundary/design contract |
| `implementation_approval` | 上述 contract + PERF bind header + DELTA hypothesis + INTERFACE contract |

下列 mutable 内容 MUST 位于 review slice 外；仅追加它们 MUST NOT 改变三闸 SHA：
TOPIC lifecycle/baseline 导航字段、PERF Numbers、DELTA Rounds、`evidence/`、
`COMMITS.md`、`GATES.md`。若结果反向修改假设、接口、绑定配置或实现边界，MUST 先修改
对应 review slice，不得借 mutable 区绕过重审。

失效矩阵：

| changed review slice | invalidated gates |
|----------------------|-------------------|
| TOPIC contract | topic_review, design_review, implementation_approval |
| DESIGN contract | design_review, implementation_approval |
| PERF bind / DELTA hypothesis / INTERFACE contract | implementation_approval |
| Numbers / Rounds / evidence / COMMITS / GATES | none |

缺标记、重复标记、错配或嵌套 MUST fail closed。旧主题 MAY 显示
`bundle_mode=legacy_whole_file`；迁移必须追加 invalidated/迁移说明并重新审核，
旧 whole-file SHA MUST NOT 验证为 review-slice SHA。

Process proposal 的 `已确认` / `已审核` 也属于人工回执，但其内容束、状态机与
stage-specific Episode 语义由 [[META-014]] 定义；MUST NOT 直接套用 POC gate
推导规则，或由 proposal 文件存在、按钮点击和 Agent acknowledged 推进状态。

## Workflow 投影与 Claude Code 委派 {#META-011}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.13 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-008,META-010 -->

可视化工作台 MUST 是树/图/git 与工具结果的派生投影，不是第五 SoT。其状态 MUST 正交展示：

主投影 MUST 是本地 NDF commander（`spec/meta/cockpit/`，React+D3）。Cursor Canvas MUST
仅为启动桥（launcher）：展示 freshness 与「Open NDF commander」，MUST NOT 把全部
POC 工作台与 Replay Prompt 嵌进 `.canvas.tsx`。每个可见控件（含 D3 点击）MUST 属于
闭集目录 `spec/meta/cockpit/action-registry.json`；snapshot MUST 输出 `enabledActions`，
UI MUST NOT 另写一套 Golden/gate/freshness 判断，也 MUST NOT 发明未登记 hop。
按钮点击 MUST NOT 充当人口令（[[META-010]]）。Composer / `openFile` 仍是可变 hop
的唯一派发面；commander 的 snapshot hop（Refresh / 打开工作台 / 查这条账）MAY 由
本地 `--serve` 重建 `tmp/ndf-canvas-snapshot.json`，MUST NOT 写 `.openclaw/state.json`。

```text
project_maturity | lifecycle | gates
spaces.design/implementation/test | agent_run | health
```

工作台 MUST 明确分离 **Business Project**（产品目标/能力/Trunk/验证/业务工作）、
**NDF Control**（Genesis/门禁/规范健康/process 工作）与 **Agent Runtime**
（session/run/worktree/lease）。存在产品 Charter 时 MUST 默认展示 Business Project；
Control/Runtime 问题仅以 blocker/badge 回传，MUST NOT 冒充产品 KPI。
提案平面 MUST 按落点目录分类：`spec/open/` 属于 Business Project；
`spec/meta/open/` 属于 NDF Control。`track` 头 MUST NOT 把产品目录文件投影到
Control，也 MUST NOT 把 meta 目录文件投影到 Product。路径与 track 不一致时
MUST 记 warning，MUST NOT 改平面。

Topic 投影也 MUST 按语义平面分面。产品 POC 的 hypothesis、业务 evidence、性能结果与
Design / Implementation / Test readiness 属于 Business Topic；gate receipt、bindcheck、
POC isolation、context verify 与 dispatch preflight 属于 topic-scoped NDF Control。
Business Topic MUST NOT 展开 Control 工具命令或原始报告；Control 结果只能以明确的
blocker/badge/pointer 回传并链接到 Governance topic filter。`perf_baseline` 的 Numbers、
baseline status、protocol 与 DELTA 状态 MAY 投影到业务 Test space，但工具执行细节仍属于
Control。分面 MUST NOT 降低 `safe_to_dispatch` 门禁：isolation/bind/context/gate 未通过
仍须 fail closed。

工作台动作 MUST 区分 `inspect → repair → refresh`，并按
`scope × Design/Implementation/Test × owner` 输出结构化 finding。每条 finding
MUST 指明证据、修复责任人、具体 task、允许写根与必要人工口令；`dispatched`
MUST NOT 冒充 `repaired` / `completed`。Topic inspect MUST 覆盖 gate SHA、完整
PERF_BASELINE、POC isolation、绑定溯源与 implementation preflight；修复后 MUST
复检并刷新投影。

责任分流 MUST 为：

- OpenClaw：装订器、门禁审计/草稿、产品或 process 提案；MUST NOT 承担产品代码实现；
- Claude Code：允许写根内的 POC 代码、隔离修复、Numbers/evidence/DELTA rounds；
- Human：gate phrase、提案确认/审核、破坏性 git 修复与产品决策；
- 工具：只读检查、Advisor 沙盒与 `tmp/` 报告；MUST NOT 静默修改 SoT。

Governance MUST 监测项目级 meta/product graph、index consistency、binder health、
gate summary 与 proposal hygiene。专项提升 MAY 委派明确 task 给 OpenClaw，但
MUST 走 process proposal 门禁。POC `safe_to_dispatch` MUST 同时要求完整性能绑定
检查与 isolation preflight 通过；未知、过期或失败均 MUST 阻止派发。

`phase_hint` MAY 用于导航，但 MUST NOT 落盘为流程真值。运行态 MUST 从 Claude Code 管道查询，
不得写入 `.openclaw/state.json` 或冒充装订器 must。

委派前 MUST 同时满足：

1. 对应人工回执有效且 approved content SHA 未漂移；
2. Claude Code 管道返回 `run_id/session_id`、`base_sha`、独立 worktree/branch
   （或可证明等价隔离）与 `allowed_write_root`；
3. 同一 topic 无其它写 run；`run_id` 作为 lease；
4. POC 写入隔离检查通过；缺任一项 MUST 显示 `unsafe` 并拒绝派发。

完成回执 MUST 含 changed files、commit SHA（若有）、复现命令与 evidence 路径；
随后 MUST 再跑写入隔离检查。运行态不写 NDF；可审计结果写 COMMITS/evidence。

POC 正结果的关闭顺序 MUST 为：

```text
promote 提案确认并落地 → 已审核 → ndf_close plan
→ Claude Code 主线集成 → index/graphcheck → 编译/性能/金标
→ TOPIC/COMMITS/NOTES/归档最终收口
```

全部验证通过前只能显示 `closing`。reject 使用 DEC/deprecated/归档分支；
partial 后 topic 仍为 `exploring`。工具 MAY 生成只读 `close-plan`，MUST NOT 静默 apply。

### OpenClaw Control 委派

NDF Control 文档流操作（legacy gate audit、GATES 审计、装订器修订、提案起草）
MUST 委派给 OpenClaw 指挥会话，而非 Claude Code 实现管道。OpenClaw 指挥会话
`session_key` MUST 在 `AGENTS.md` 显式配置；Canvas/工具只读该配置，MUST NOT 硬编码。

Runtime 投影 MUST 分离两路 agent：

```text
runtime.implementation — Claude Code ACP（代码/证据/DELTA Numbers）
runtime.control        — OpenClaw（装订器/门禁/提案/按需读 spec/meta）
```

`ndf_workflow_status.py control-pack` MAY 生成只读 Control 委派包（schema
`ndf-control-pack/v1`），含 topic、`phase_hint`、gate bundle SHA、`required_reads`、
`allowed_write_roots` 与 `next_human_phrase`。任务类型：`legacy_gate_audit`、
`gate_sha_audit`、`gate_receipt_draft`、`binder_amend`、`control_proposal`、
`gate_pipeline`、`binder_pipeline`。

Control 动作 MUST 硬分两套流水线，禁止混称：

| 流水线 | 叫法 | 步数 | 主任务 | 真值 |
|--------|------|------|--------|------|
| A 人工门禁 | **闸 / gate**（唯一称「闸」） | 3 | `gate_pipeline` | `GATES.md` + 人口令 |
| B 装订器修订 | **面 / binder facet**（禁止称「闸」） | 6 | `binder_pipeline` | 装订器文件/字段缺口 |

顺序：A 为 `TOPIC已审核` → `DESIGN已审核` → `可以开始实现`；
B 为 TOPIC → DESIGN → PERF_BASELINE → DELTA → INTERFACE → COMMITS（[[BEH-025]]）。
分步 finding 可保留 `legacy_gate_audit` / `binder_amend` 作为焦点步，但 Canvas MUST
提供流水线主按钮；整条流水线 SHOULD 只派发一次 Cursor→OpenClaw，分步按钮 MUST
优先 resume 本流水线 Episode，MUST NOT 默认每次全量重派。A 与 B MUST 使用各自
Episode（或同 Episode 但事件 MUST 带 `pipeline=gate|binder` 与 step id）；MUST NOT
混跑成无标签超级派发。B 可挡住 A 的下一闸，投影 MAY 提示依赖，修复动作仍走各自
流水线。A 每闸 MUST 停人口令；B 默认无口令，写完后 MUST 复检 topic-health。

#### Control 双流水线写入所有权与交接

两条流水线 MUST 保留独立真值与写入所有权：

| pipeline | MAY 写 | MUST NOT 写 |
|----------|--------|----------------|
| `gate` | `GATES.md` 的 audit / pending / invalidated 回执与门禁说明 | TOPIC、DESIGN、PERF_BASELINE、DELTA、INTERFACE、COMMITS 正文 |
| `binder` | 当前 facet 对应装订器文件/字段；完整 facet 可 audit + no-op recheck | `approved_by`、`gate.confirmed`、关闭决定 |

1. `gate_pipeline` 遇到下一闸 bundle 缺文件或字段时 MUST 停止并输出
   `blocked_by_binder`、`next_binder_facet`、`blocked_gate`；Canvas MUST 提供对应
   binder 面动作。Gate Agent MUST NOT 代写缺失 facet。
2. `binder_pipeline` 完成一面后 MUST 复检；若 facet 已完整，MAY 记录 no-op
   `binder.audit → binder.recheck`，不得为证明流水线存在而重写内容。
3. Gate pack 的精确写入面 MUST 限定为该 topic 的 `GATES.md`（以及 gitignored
   gate receipt/event）；binder pack MUST 按 focus facet 限定文件面。
4. completion 声明若含跨 pipeline 文件 mutation，MUST fail closed 并报告
   `cross_pipeline_write`，不得投影为已完成。

文件级边界之外还 MUST 执行 section-level 所有权：

| owner/pipeline | MAY 写 | MUST NOT 写 |
|----------------|--------|----------------|
| Gate/OpenClaw | GATES audit/pending/invalidated/approved receipt（人口令后） | 任一 binder 正文 |
| Binder/OpenClaw | review slice 草稿、绑定骨架、接口骨架 | PERF Numbers、DELTA Rounds、evidence、关闭决定 |
| Claude Code | POC code、测量、PERF Numbers、DELTA Rounds、evidence、COMMITS append | L0/L1/meta、人口令回执 |

Control/implementation pack MUST 输出 `allowed_sections`；仅有路径权限不足。completion
或 pipeline step 修改越权 section 时 MUST 报 `cross_role_section_write` 并 fail closed。
Binder 对完整 contract MAY no-op recheck，不得为“修健康”伪造 Numbers。OpenClaw
生成的性能叙述若无 Claude Code completion + measure/evidence receipt，MUST 标
`unverified`，不得更新 baseline current。

业务编排 MUST 结构化交错，不得由 gate 顺手完成 binder：

```text
binder.TOPIC → gate.topic_review
→ binder.DESIGN → gate.design_review
→ binder.PERF_BASELINE/DELTA/INTERFACE → gate.implementation_approval
→ human decision → implementation / continue / close
→ binder.COMMITS append
```

`COMMITS.md` MAY 在实现前创建 ledger 骨架；实际代码/验证 commit 产生后再追加。

#### 门禁完成、探索决策与关闭资格

1. 三闸全部有效只产生 `decision_required`，MUST NOT 自动产生
   reject/promote/partial/close。
2. 下一决策 MUST 由 Human 显式选择：

   ```text
   implement | continue_exploring | amend | promote | partial | reject
   ```

3. `close_eligible` MUST 由结构化当前事实推导：lifecycle、显式选择、适用的
   proposal/DEC、close-plan 与验证回执。DESIGN/GATES/NOTES 中的「建议关闭」
   「负结果」自由文本 MUST NOT 单独令其为 true。
4. lifecycle 为 `exploring|blocked` 且历史负结果之后出现新假设/新前提时，
   投影 MUST 为 `decision_required` 或 `continue_exploring`，并保留旧 round；
   仅已 `rejected|promoted` 的主题适用 [[BEH-025]] 平级新 topic 规则。
5. 用户选择继续同一假设/协议时 MAY amend 当前 topic；实质修改门禁 bundle 后，
   MUST 按 [[META-010]] 追加 `invalidated` 并重新审核受影响闸，不得改写旧回执。

OpenClaw Control 委派写边界：

| 可写 | 禁止 |
|------|------|
| `poc/<topic>/ndf/` | `src/`、`include/`、`tests/` |
| `spec/open/`、`spec/meta/open/` | `spec/meta/` 正文 |
| `.openclaw/state.json` | 静默写 `GATES.md` 的 `approved_by` |

Canvas Topics 在 gate 相关 `phase_hint` 时 MUST 提供 OpenClaw Control 动作
（audit SHA、legacy audit、gate draft、**门禁流水线**），装订器缺口时 MUST 提供
**装订器流水线**，MUST NOT 将实现派发（`pack`）冒充 Control。
audit / pipeline 启动类任务 `safe_to_delegate` 恒 true；写 GATES 草稿时若 gate 已
`invalidated` MUST 拒绝委派。门禁口令仍由人触发；Canvas/Composer 桥接 MUST NOT 代批。

#### Control 流水线一键派发

Canvas 不能直接执行 shell / MCP，但 `启动门禁流水线` / `启动装订器流水线` 创建的
Cursor 桥接任务 MUST 以 OpenClaw 的可验证接收回执为派发终点，而非以
`newComposerChat` 创建成功为终点：

```text
requested → pack_created → context_verified
→ openclaw_sent → openclaw_acknowledged
→ waiting_human | running | blocked → post_action_sync
```

1. 启动动作 MUST 创建或续接显式 Episode、生成对应 `control-pack`、校验 Manifest /
   OpenClaw role plan，并调用 `openclaw.chat_send`；Cursor 桥接任务 MUST NOT 在
   `openclaw.chat_send` 之前结束。
2. 只有获得 OpenClaw 返回值并记录同一 Episode 的 `openclaw.request` /
   `openclaw.response`（最低 `messages_only` coverage）后，投影才可显示
   `acknowledged`。仅创建 Composer 对话 MUST NOT 显示“流水线已启动”。
3. MCP 不可达、pack/context 无效或无 OpenClaw 回执时 MUST 显示 `blocked`，保留
   blocker 与“重试派发”入口。
4. 主按钮为整条流水线的一键派发；分步按钮有活跃 Episode 时 MUST resume 同一
   OpenClaw 会话；无活跃 Episode 时 MUST 先完成相同桥接状态机。
5. 门禁流水线每闸 MUST 停在准确人口令；装订器流水线 MAY 连续完成 POC NDF/
   工作流准备，但每面完成后 MUST 复检，MUST NOT 代批门禁或顺带派发 Claude Code。

`control-pack` MUST 含 `workspace` 绑定（`repo_root`、`repo_head`、`active_topic`、
`topic_dir`）。OpenClaw 收到委派后 MUST 将 `workspace` 写入 `.openclaw/state.json`；
后续回合即使会话上下文丢失，MUST 先读 `state.json.workspace` 再操作文件。
`workspace` 是项目锚点，不是 Claude Code `run_id` 运行态；运行态仍只从管道查询。

### Per-Project Workspace 绑定

`.openclaw/state.json` 是**仓库本地**指挥状态（`{repo_root}/.openclaw/state.json`），
MUST NOT 与 OpenClaw gateway 全局 session store（`~/.openclaw/agents/...`）混淆。

**所有**委派 pack（`control-pack`、`pack`、`genesis-pack`）MUST 含统一 `workspace` 块：

```text
repo_root | repo_name | repo_head | state_path | active_topic | topic_dir | topic_ndf_dir
```

规则：

1. `state_path` 相对 `repo_root`，默认 `.openclaw/state.json`。
2. OpenClaw 收到 pack 后 MUST 写入 `{repo_root}/.openclaw/state.json` 的 `workspace`。
3. Claude Code 收到 pack 后 MUST 在 `{repo_root}` 下建立/使用 worktree；`allowed_write_root`
   MUST 在 `repo_root` 下解析；start handshake MUST 含或可证 `repo_root`。
4. 切换本地项目 = 切换 `repo_root`；MUST NOT 在无 `repo_root` 时操作文件。
5. 相对路径（`poc/...`、`spec/...`）MUST 在 `workspace.repo_root` 下解析，不得假设 agent cwd。

### Interactive Close Console

Canvas MAY 提供 Close 交互操作台，收集 topic、mode、step 与用户补充指令，并按关闭顺序
委派 OpenClaw / Claude Code。该操作台仍是派生投影，MUST NOT 冒充实时 Agent runtime，
MUST NOT 将本地 UI history 当作 NDF SoT。

1. Canvas `newComposerChat` 仅表示 `dispatched`；无工具/文件证据时 MUST NOT 标
   `completed`。
2. 人工口令仍由人触发；操作台 MUST NOT 静默批准门禁或越过 proposal / close-plan /
   verification。
3. 每个 Close operation MUST 以 `POST_ACTION_SYNC` 结束：重跑 workflow snapshot，
   更新整个 Canvas；失败 MUST 显示 blocker，后续步骤保持 pending。
4. snapshot MAY 输出只读 `control.close`，但未知 graph/build/perf/golden 状态 MUST
   显示 `unknown`，不得推断为通过。
5. Canvas 不能直接执行 shell/MCP；实际回复仍在 Composer。若无法完成同步，MUST 提供
   显式 Refresh dashboard 恢复入口。

### 可验证投影刷新

Canvas 发起的、可能改变本地 tree/git/tool 证据的操作 MUST 使用本地 append-only action
receipt，并在操作成功或失败后重算完整 snapshot。回执是运行审计证据，不是产品或 process
SoT；默认位于 gitignored 的 `tmp/ndf-workflow-actions.jsonl`，MUST NOT 写入
`.openclaw/state.json` 冒充 Agent runtime。

终态回执 MUST 至少记录：

```text
action_id | topic | operation | started_at | finished_at | result
repo_head_before | repo_head_after | snapshot_sha_after | blockers
```

snapshot MUST 输出 `projection_freshness`，状态语义如下：

| 状态 | 含义 |
|------|------|
| `fresh` | 当前投影 generation 覆盖最新终态 action |
| `refresh_in_progress` | 存在已开始但无终态回执的 action |
| `stale_after_action` | 最新终态 action 尚未被当前投影吸收 |
| `unknown` | 无法获得可验证 action/runtime 证据 |

Canvas dispatch MAY 先用本地 UI state 显示 `refresh_in_progress`，但最终状态 MUST 来自工具
投影。若平台不能订阅本地 snapshot artifact，Composer action MUST 在退出前生成新 snapshot
并更新整个 Canvas；同步失败时 MUST 显示 stale banner，不得继续把旧投影表达为 ready /
closed。自动刷新只更新派生投影，MUST NOT 自动批准人类 gate、写 stable 契约或绕过
proposal / close-plan / verification。

只有 `fresh` 且相关 verifier 明确 `passed + current` 的投影 MAY 启用对应写动作；
`refresh_in_progress`、`stale_after_action`、`unknown`、`not_run`、malformed action
或旧 kernel map MUST fail closed。NDF Control 的主要区域 MUST 以白盒信息链呈现：

```text
applicable_clauses | dependency_edges | computed_state
evidence_refs | source_generation_sha | project_impact
owner | next_action
```

摘要状态 MUST 可下钻到条款、source path、content SHA 与 receipt/verifier；只给红黄绿
结论不得作为上层本地项目的工作依据。Control finding 向 Product/Topics handoff 时 MUST
保留 scope、规则、证据、owner 与安全动作，MUST NOT 冒充产品 KPI 或替人类作产品决策。

### 业务驾驶舱最低呈现

Canvas SHOULD 直接消费 workflow snapshot（或官方 Canvas JSON 适配），不得另行硬编码
活跃 topic、业务风险或 close 状态。业务驾驶舱至少 SHOULD 展示：

1. Product-scoped Now / Next / Blocked 与 snapshot/action generation；
2. Design / Implementation / Test 独立 `ready` 与 gaps；Numbers pending、baseline stale、
   gate `legacy_unknown|invalidated` 时不得显示绿色 ready；
3. snapshot `business.risks`、Genesis G0→G3、DELTA/traceability；
4. promote/partial/reject 分支与 evidence-backed finalize 门禁；
5. Runtime 未探测时为 `unknown|unavailable`，不得推断 idle。

## NDF 任务上下文与证据绑定 {#META-012}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.14 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-002,META-008,META-010,META-011 -->

Canvas、OpenClaw 与 Claude Code MUST 使用同一份带 SHA 的 Task Manifest，并从中派生
各自的 role-specific Context Plan；不同 role plan SHA MAY 不同，但 MUST 引用同一
`manifest_sha`。任务上下文 MUST 按以下顺序机械组装：

```text
BinderReadOrder → NDFGraphClosure → Git/ImplementationSurface
→ Evidence/Baseline → Gate/RuntimeLease → RoleSpecificPrivilege
```

1. Binder MUST 先按 [[BEH-025]] 读序；clause seed MUST 来自 TOPIC、提案、ledger /
   trailers、task 默认条款或 close plan，禁止仅凭自由文本猜测。
2. 图默认只沿 `depends-on` / `refines` 展开；其它边 MUST 按 task 明确启用。
   traversal MUST 有 depth/node/byte budget，截断 MUST 报告。
3. Task Manifest MUST 绑定 task、track、topic、repo HEAD、共享图/evidence/gate；
   Context Plan MUST 绑定 manifest SHA、role、source generation、
   gate bundle、baseline、ordered reads、图策略、允许写根、禁止路径与人工口令。
4. Context Bundle MUST 绑定 plan SHA、每个文件/条款 chunk SHA、git/evidence joins；
   Agent 执行前 MUST verify，漂移时 MUST 停止并重新编译。
5. 默认 bundle MUST NOT 从 NOTES / stable SLA 抄 POC 观测数字；仅显式测量 task
   MAY 读取 PERF_BASELINE Numbers。
6. OpenClaw 只接收 Control 文档流 role plan；Claude Code 只接收 Implementation/Test
   及对应已批准契约 role plan；Canvas 只显示 Manifest 与角色切片摘要，不成为第四上下文 SoT。
7. Task Manifest MUST 绑定 Context Compiler 的派生证明（compiler identity/version、
   compiler policy、seed/binder/graph/evidence 输入摘要，以及 closure、truncation、
   conflicts、baseline、blockers 与 role policy 的派生摘要）。验证 MUST 使用同一 policy
   重新派生语义；只对调用者提供内容重算 `manifest_sha` 不足以证明 Manifest 合法。
8. Role Plan MUST 校验 `role × task × track` 兼容矩阵：OpenClaw 仅接收 Control 文档流；
   Claude Code 仅接收 Implementation/Test 与明确批准的集成面；Canvas 仅作只读投影与编排。
   不兼容角色 MUST fail closed，不得仅依赖空写根偶然阻止执行。
9. Task Manifest / Context Plan MUST 绑定
   `bundle_mode | slice_id/path/content_sha | allowed_sections | mutable_sections`。
   Context verify MUST 重算 slice SHA；legacy whole-file 与 review-slice plan 不兼容，
   MUST NOT 在同 Episode rebind。
10. Project-control 任务 MUST 额外绑定 `proposal_id | flow_id | hop | origin`，以及
    `intent_sha` 或 `proposal_path + proposal_sha`。role plan MUST 校验
    `role × task × track × stage`；内容或 hop 漂移时 MUST 创建新 Manifest，
    不得在同 Episode 仅重算哈希后继续。

委派 readiness MUST 分离：

```text
static_preflight_passed | runtime_dispatch_ready
```

前者覆盖 gate / baseline / perf / isolation / context verify；后者覆盖 pipeline、
同 topic lease、run/session/base/worktree/allowed-root 握手。缺任一项 MUST 拒绝写派发。

所有 writable pack MUST 显式绑定 Episode、Task Manifest、对应 role plan 与 exact
`allowed_write_root`；缺任一项时 `safe_to_dispatch=false`。工具 MUST NOT 对可写 pack
静默省略 Episode 记录或降级为未绑定派发。

所有可使 projection、Close 或 Agent 状态变绿的 receipt MUST 绑定：

```text
schema | task | topic | mode | step | repo_head | source_generation_sha
manifest_sha | context_plan_sha | command | input_sha | output_sha | evidence_paths
started_at | finished_at | result | blockers
```

旧短 gate SHA、裸 `tmp` 报告、NOTES-only evidence 或未绑定 action 只能显示
`legacy_weak|legacy_unbound|unknown`，MUST NOT 完成 gate、Close 或 dispatch。
Cursor / Canvas / context 工具 MUST NOT 修改 `.openclaw/state.json`；runtime lease
只写 gitignored 临时证据。

Runtime lease 在 live worktree 校验成功时 MUST 保存 acquisition-time durable binding
proof；completion MUST 以 acquisition/completion 双快照证明 tracked、untracked 与
越界 mutation，并使实际变化集合与声明的 `changed_files` 双向一致。Close/post-check
receipt MUST 绑定注册 verifier 的绝对身份、argv/version、真实退出码与结构化输出；
任意 evidence bytes 加自报 `passed` 不得使状态变绿。

## Agent Episode、事件链与回放等级 {#META-013}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.15 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-010,META-011,META-012 -->

Context Plan 是 Agent 的执行输入 IR；Agent Episode 是输入、事件、观测与结果的可审计
时间 DAG。两者 MUST NOT 混为一物。每次可写 Agent 委派 MUST 创建或续接显式 Episode，
并绑定同一份 `ndf-task-manifest/v1`。Canvas、OpenClaw 与 Claude Code MAY 从该 Manifest
派生不同 role plan，但每个 plan MUST 引用同一 `manifest_sha`，不得把一个角色的 plan
冒充另一角色的真实上下文。

Episode MUST 使用内容寻址对象保存 manifest、context、dispatch pack、gate、runtime lease、
model/tool 可见面、filesystem/git mutation、completion 与 verification receipt。对象、tree、
commit、parent、ref、tag 与事件链 MUST 可由 canonical SHA 验证；事件 MUST 含 monotonic
`seq`、`prev_event_sha` 与 `event_sha`。旧无链证据只能作为 `legacy_import` /
`legacy_unbound`，MUST NOT 进入 verified Episode commit 或使状态变绿。

回放 MUST 显式声明等级：

| 等级 | 合同 |
|------|------|
| R0 Audit | 不执行模型或工具；精确重建已存对象、事件顺序、上下文、门禁、观测与结果 SHA |
| R1 Observation | 使用记录的 model response 与 tool cassette 重建 Agent 所见；无外部副作用 |
| R2 Sandbox Outcome | 在绑定 git/worktree 与显式沙盒 profile 中、经 `bwrap` 或 `vm`（Lvm）adapter 重跑允许命令；文件/spec SHA 精确，性能按协议容差；无可用 adapter 时只能 `environment_blocked` |
| R3 Counterfactual Fork | 更换模型、上下文、假设或观测并创建新分支；MUST NOT 宣称复现原历史 |

重新调用模型属于 R3，不属于 R0/R1。Replay MUST NOT 承诺逐 token 确定性，不保存或
伪造隐藏 chain-of-thought；不可见 system surface、远端状态或未捕获 runtime stream MUST
标为 coverage gap。

Tool cassette MUST 保存 Agent 实际可见的规范化调用、输入、stdout/stderr blob SHA、
exit status、cwd/worktree、环境 allowlist 指纹、外部资源版本与 replay policy。远端/MCP
默认 `recorded-only`；写工具仅可在显式隔离沙盒中 live replay。secret 与环境值 MUST NOT
写入普通对象或 share-safe export。

Compaction MUST 创建 `ndf-replay-checkpoint/v1` commit，绑定覆盖事件范围、raw digest、
保留对象、重新编译的 manifest/plan 与 open decisions；MUST NOT 覆盖或删除父事件。
summary 只用于导航，MUST NOT 单独用于 dispatch、gate 或 Close。恢复会话时 MUST 重新
verify manifest、Context Plan、gate 与 repo HEAD。

Replay store 是 gitignored 本地/受控 artifact evidence，不是新的产品或 process SoT。
关闭或晋升 MAY 在装订器 `REPLAYS.md` 中记录小型 manifest、tip SHA 与 evidence 指针，
不得把大型 transcript/blob 写入产品规范树。redacted export MUST 创建新 tree/commit 和
redaction map，不得修改原对象。

Cursor / Canvas / replay 工具 MUST NOT 修改 `.openclaw/state.json`。自动捕获必须通过
显式 Episode 参数启用；平台只提供 completion 时 MUST 标 `completion_only`，不得用事后
summary 冒充完整事件流。Canvas Replay 仍是派生投影，MUST 分开呈现 R0/R1/R2/R3；
R2 MUST 显示沙盒、网络、写根、副作用与成本确认。Canvas 主路径「已回放」MUST 遵循
[[META-015]]（Lvm guest-proof）；提示词 / 同机 worktree / 仅 `bwrap` 观测 MUST NOT
标为已回放。

### Historical audit 与 current readiness

Replay MUST 将历史验证与当前恢复验证分离：

```text
historical_integrity | historical_semantics
current_restore_ready | current_dispatch_ready
```

1. R0 historical audit MUST 只依赖内容寻址对象、记录快照与 durable proof；当前 HEAD、
   当前 gate 漂移或历史 worktree 已清理 MUST NOT 把原本合法的历史判坏。
2. checkpoint 恢复、R2 与再次派发 MUST 另跑 current readiness，显式报告 repo/file/gate/
   environment/worktree drift；MUST NOT 用 historical green 代替当前可执行。
3. R0 reconstruct MUST 遍历目标 commit 的完整 parent DAG，保留 branch provenance、
   branch-local event order 与 merge parents；只遍历目标 tree 或按时间戳拼接后宣称
   “完整 Episode”均不合法。
4. `fsck` MUST 验证 commit/tree/parent/ref/tag 的对象类型、parent DAG 无环、
   event-chain branch/命名/payload 一致性与 redaction lineage；引用存在但类型错误
   MUST fail。

### Episode 语义状态机

verified Episode MUST 校验关键事件的 actor、payload identity、前置状态与合法后继：

```text
manifest.created → context.compiled → context.verified
→ gate/proposal confirmed → dispatch.preflight → lease.acquired
→ model/tool/filesystem/git events → completion → lease.released
→ verification/close → checkpoint/merge
```

Control 双流水线分步事件（[[META-011]]）MUST 可独立回放，不得合成一条含糊 completion：

```text
pipeline=gate:   gate.audit → gate.draft → gate.confirmed   # × 每闸 id
pipeline=binder: binder.audit → binder.amend → binder.recheck  # × 每面 id
```

`gate.confirmed` / `gate.approved` 的 actor MUST 为人类；`gate.audit` / `gate.draft` 与
`binder.*` 的 actor MUST 为 openclaw（或 tool 代记）。MUST NOT 将 3 闸与 6 面合并为
一句「Control 已处理」。同会话多步合法；缺 `pipeline` + step 身份不合法。

Gate→Binder 交接 MUST 记录结构化 handoff 事件，至少绑定：

```text
pipeline | blocked_gate | next_binder_facet | manifest_sha | context_plan_sha
```

Gate Episode completion MUST 校验 filesystem mutation 仅落在 gate 写入面；Binder Episode
同理校验 focused facet，跨面修改必须由 pack 显式授权。`gate.confirmed` 与
`decision.selected` 是不同事件；前者 actor=human 不推出后者。历史结论与当前决策 MUST
分别回放，不得将散文中的 reject 建议合成为 `decision.selected(mode=reject)`。

Gate receipt/event MUST 记录 `bundle_mode` 与 slice manifest SHA。Replay diff MUST
区分 `contract_slice_changed` 与 `mutable_evidence_changed`。测量结果进入 verified
Episode 必须有 Claude Code run/lease/completion 与真实 measure/evidence receipt；
OpenClaw 文档修改不得冒充测量事件。从 `legacy_whole_file` 迁移到 `review_slice`
MUST 创建新 Episode / Manifest。

Control 流水线一键派发 MUST 将 pack、request、response 与后续 pipeline step 绑定到
同一 Episode。回放 MUST 区分 Composer 任务创建、pack/context 完成、MCP 请求发出、
OpenClaw 确认与后续分步修改。`openclaw_sent` 无匹配 response 时只能是未完成派发；
恢复时 MAY 按同一 request identity 幂等重试，MUST NOT 因重试重复创建门禁批准或
重复声称流水线已启动。无 response/receipt 的 action MUST NOT 进入 acknowledged。

Process proposal 的 project-control 回放 MUST 另按 [[META-014]] 区分
`draft` / `confirm_land` / `review` child Episode。每个 child MUST 有自己的 Manifest /
role plan 与 stage 写入面；`context.verified` 必须先于 `dispatch.preflight`。
request timeout 只能进入 `delivery_unknown`；同 identity 重试递增 attempt，匹配的迟到
响应 MAY 对账为 `acknowledged`，身份或结果冲突 MUST fail closed。

通用 `record` 入口写入的未语义验证事件只能进入 unverified history。malformed action /
event 不得被静默丢弃后产生 green；projection freshness MUST 证明最新终态 action 已被
snapshot 吸收，并使用 [[META-011]] 定义的状态语义。

### R1 / R2 / checkpoint / export 加固

1. R1 MUST 重建完整 recorded observation surface 并校验每个 observation 的 replay
   policy；MUST NOT 与 R0 仅更换等级标签。
2. R2 MUST 精确选择目标 run/role/manifest 的 plan，并校验 cassette 的 environment
   fingerprint、cwd 与 tool/runtime version；exact、epsilon、write violation 与
   context/gate drift 均须有负例。执行 adapter MUST 为 `bwrap` 或 `vm`（Lvm，见
   [[META-015]]）。宿主不能执行隔离 adapter 时只能标 `environment_blocked`，不得记
   passed，也不得退回宿主 Composer 执行回放体。
3. checkpoint MUST 覆盖完整 merged DAG 并保留足够对象用于恢复；summary-only state
   MUST NOT dispatch。
4. share-safe export MUST 结构化识别相邻 argv secret、header、URL credential 与 env
   assignment，对完整导出闭包执行 secret/PII scan；非零 finding MUST 拒绝 share-safe ref。
5. Canvas MUST 展示 evidence-specific R2 profile 与实际 manifest/context/gate/
   verification 摘要；diff MUST 分开 manifest、context、events、observations、results
   与 verification。R0/R1 若只能经 Composer 生成指令，MUST 标为 instructions，
   不得显示为 Replay 已执行。Canvas hop/prefix 回放 MUST 只启动宿主 `guest-run`
   launcher（[[META-015]]），不得在现仓 cwd 执行 reconstruct 回放体。

## 回放沙箱与执行器边界 {#META-015}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.17 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-011,META-013 -->

回放沙箱是**执行器边界**，不是提示词标签。一条回放「已执行」成立，当且仅当：

1. **执行器不在现仓。** guest 的 cwd / checkout 不是宿主 `repo_root`。
2. **现仓对 guest 不可写。** MUST NOT 将现仓以可写共享挂载进入 guest；注入 MUST 使用
   快照拷贝或只读介质。
3. **出站通道只有回执（默认）。** guest 默认无网络；需要外部 API 时 MUST 使用合同内
   egress allowlist，否则 guest 只做 R0/R1（不调模型）。重新调用模型仍属 R3
   （[[META-013]]）。
4. **回执可证伪。** 宿主 MUST 产出 `ndf-replay-guest-proof/v1`；至少含 `guest_id`、
   `image_sha`、`guest_toplevel`、`host_toplevel`、`adapter=vm`，且
   `same_checkout=false`、`host_tracked_unchanged=true`、`host_head_unchanged=true`、
   `bwrap_used=false`、reconstruct `side_effects=false`。缺项、`same_checkout=true`、
   宿主 tracked 变化、guest marker 出现在宿主根、或 `host_mount_used=true` →
   `valid=false` / `environment_blocked`，不得宣称回放已执行。
5. **分级不得混称：**

| 级别 | 是什么 | 可否当「已回放」 |
|------|--------|------------------|
| Lsoft | 提示词 / Control 信封 | 否，只是 instructions |
| Lns | 同机 worktree / `bwrap` | 否（降级观测） |
| Lvm | guest 虚拟机 + guest 内执行器 | 是，Canvas 主路径 |

Hypervisor 是实现 adapter，条款 MUST NOT 写死专名。无可用 Lvm 后端时 MUST fail
closed，MUST NOT 退回宿主对话代理在现仓执行回放体。

宿主（Canvas / `guest-run`）只准：按 recorded `repo_head` 做只读快照、启动 guest、
传入 episode/commit 与只读 replay store 拷贝、等待回执、销毁 guest、展示 JSON。
宿主 MUST NOT 把可写委派的组装 prompt 当作回放体在现仓执行。「写回当前工作区」是
可选危险第二步，默认关闭，不在 guest 合同内。

R2 执行 adapter MUST 为 `bwrap` 或 `vm`。Canvas 主路径以 `vm`（Lvm）为准；`bwrap`
仅作降级观测，不得冒充「已回放」。

## Process Proposal 生命周期与回执 {#META-014}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.16 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-010,META-011,META-012,META-013 -->

NDF Control 对新托管 process proposal 的白盒投影与受控委派 MUST 使用同一 canonical
生命周期：

```text
pending_confirmation
→ confirmed_pending_land
→ implemented_pending_review
→ reviewed
```

`rejected` / `superseded` 为终态；archive 只是存储位置。旧 `Status: Implemented on ...`
与 `reviewed: 已审核` 只作为兼容输入；缺现代回执时 MUST 投影为
`legacy_pending_unknown | legacy_implemented_unbound | legacy_reviewed_unbound |
legacy_rejected_unbound | legacy_superseded_unbound`，不得自动完成 gate 或产生可写 hop。

### 人工回执

`proposal.confirmed` / `proposal.reviewed` MUST 是 append-only 结构化回执，并至少绑定：

```text
proposal_id | flow_id | hop | phrase | actor | approved_at
proposal_sha | source_ref | status
```

actor MUST 为 Human，phrase 分别为精确口令 `已确认` / `已审核`。Agent/Canvas
acknowledged、按钮点击、Composer 对话创建或文件存在 MUST NOT 推进生命周期。
proposal 内容漂移后，下游回执 MUST append `invalidated`，不得改写历史。

### Stage 权限与 child Episode

一个 `flow_id` MUST 使用三个权限不同、不可变的 child Episode：

| hop | MAY 写 | MUST NOT 写 |
|-----|--------|----------------|
| `draft` | 预先确定的单一 proposal 文件 | stable META、实现、审核回执 |
| `confirm_land` | 当前 proposal 与 Manifest 绑定的 `land_targets` | 未声明路径、审核回执、产品实现 |
| `review` | 当前 proposal 的 review marker / 绑定回执 | 重写已落地 META 或实现 |

每个 hop MUST 重新绑定当时的 intent/proposal/人口令 SHA、repo HEAD、Task Manifest 与
role plan。前一 hop 修改内容后 MUST 创建新 child Episode / Manifest；MUST NOT 在同一
Episode rebind 后继续。实际 mutation MUST 与 stage 声明写集双向一致；越权、少报或多报
均 fail closed。

### Dispatch 与幂等对账

Project-control dispatch MUST 使用：

```text
requested → pack_created → context_verified → sent
→ acknowledged | delivery_unknown | blocked
→ waiting_human | running | succeeded | failed
```

只有 verified Context Plan 才能产生 `dispatch.preflight`。request/response MUST 绑定同一
`request_id`、Episode、Manifest 与 intent/proposal identity。timeout MUST 进入
`delivery_unknown`；重试保持 request identity 并递增 attempt。匹配的迟到成功 MAY
对账为 `acknowledged`（迟到标记只作 reconciliation evidence，不是另一套主状态）；
身份或结果冲突 MUST fail closed，且不得重复批准或 mutation。

### 平面与历史隔离

产品 graph/proposal finding 属于 Product；binder/topic finding 属于 Topics；META
graph/index/process proposal 才属于 NDF Control。`spec/meta/open/draft-map/**` MUST NOT
扫描成 process proposal/hop；其现行 warning 只读投影，Canvas MUST NOT 自动修改映射。
历史 proposal 只有在人明确选择“纳入 Control flow”后才 MAY 创建迁移 Episode，
MUST NOT 批量伪造旧确认或审核。

`.openclaw/state.json` 只承载 workspace 绑定与 OpenClaw 指挥进度，MUST NOT 承载
proposal/gate receipt、projection freshness、runtime lease 或 Replay 真值。

> rationale: NDF Control 的目标是让用户白盒看到“规则—证据—项目影响—下一步”。
> proposal 状态机与信任链用于证明投影，不是新的 SoT，也不得成为隐藏式自动治理器。

## 负结果与回退 {#BEH-020}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->
<!-- ndf: refines=CHR-008 depends-on=DEF-022 -->

当探索证伪（样板：产品负结果 DEC）时 MUST：

1. 写/更新产品 `spec/decisions/`（负结果、根因、废弃条款列表）；DEC 正文或 commit 含
   `Rejects: <topic>`
2. 将相关 draft/stable 探索条款标 `deprecated` 或移出 must；关闭产品 `open/proposal-*` /
   装订器内提案为 Rejected/Superseded
3. **Trunk `src/`**：删除或永不合并该 POC 表面；若曾误合入，用显式 revert commit（引用 DEC）
4. **`poc/<topic>/`**：可保留失败复现至下一归档周期；**默认**将 `poc/<topic>/ndf/`
   整包迁入 `spec/archive/YYYY-MM/poc-<topic>/`（防踩坑）；`TOPIC.md` status → `rejected`。
   若存在 `NOTES.md`，MUST 将文件头 status 与 TOPIC 对齐为 `rejected`（日期/`Rejects`
   DEC；见 [[BEH-025]]）
5. 仅当条款曾写入 `spec/` draft 时，主线 MUST 保留 `deprecated` 壳并指向归档装订器
6. MUST NOT 要求改写已推送的探索 commit 历史来「对齐文档」——以 DEC + 当前树为准
7. 负结果关闭后若再探索同一方向：见 [[BEH-025]]「关闭后重启」——MUST 开平级新 topic；
   MUST NOT 将 `rejected` 主题 status 改回 `exploring`/`blocked`（原地复活）

## POC 主题装订纪律 {#BEH-025}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: refines=BEH-018,ARCH-008 depends-on=DEF-022,DEF-023,CON-POC-001 -->

每个活跃探索主题 `poc/<topic>/` MUST 维护装订器目录：

```text
poc/<topic>/ndf/
  TOPIC.md
  DESIGN.md
  PERF_BASELINE.md
  DELTA.md
  INTERFACE.md
  GATES.md        # 人工回执（新主题；历史主题可无）
  proposals/     # 本主题提案正文，或 stub 指回 spec/open/
  evidence/      # validation / 对照表
  COMMITS.md     # Commit Ledger [[DEF-023]]
```

### 呈现规则（唯一入口与阅读顺序）

- `poc/<topic>/ndf/` MUST 作为 POC 内唯一规范性呈现面；如存在 `poc/<topic>/README.md`，MUST NOT 作为 must 源（仅允许导航指针）。
- 协作者在 POC 内获取 NDF 的推荐阅读顺序 MUST 为：
  1. `poc/<topic>/ndf/TOPIC.md`
  2. `poc/<topic>/ndf/DESIGN.md`
  3. `poc/<topic>/ndf/PERF_BASELINE.md`
  4. `poc/<topic>/ndf/DELTA.md`
  5. `poc/<topic>/ndf/INTERFACE.md`
  6. `poc/<topic>/ndf/GATES.md`
  7. `poc/<topic>/ndf/proposals/`（或 stub → `spec/open/`）
  8. `poc/<topic>/ndf/evidence/`
  9. `poc/<topic>/ndf/COMMITS.md`

### 分段门禁与 GATES

新开题 / 平级重启 MUST 按：

```text
TOPIC已审核 → DESIGN已审核 →（PERF 绑定 + DELTA）→ 可以开始实现
```

执行。对应回执 MUST 写入 `GATES.md` 并符合 [[META-010]]。未收到「可以开始实现」或
回执 SHA 已失效时，MUST NOT 编写/委派主题代码。历史 POC 不强制回填，Canvas 显示 legacy。

### TOPIC.md

MUST 记录至少：`topic_id`；`status` ∈ {`exploring`,`blocked`,`promoted`,`rejected`}；
`baseline_protocol`（如产品树现行验收协议路径 + 数据集/线程）；
`explore_surface`（逗号分隔短标签，开题 MUST；例：`fine-rerank` / `page-cache-l4` /
`pq-codes` / `mt-scaling`）；
`baseline_trunk_sha`（首次 R0 后 MUST：当时 Trunk `src` 短 SHA）；
`baseline_status` ∈ {`current`,`stale`,`n/a`}（R0 后默认 `current`；关闭主题可用 `n/a`）；
`proposals[]`（路径、Status、角色 root/amend/process-hygiene）；`draft_clauses[]`；
`active_hypothesis` / `next_gate`；可选 `depends_on_topics[]`；互斥时 MUST
`conflicts_with_topics[]`。

### NOTES.md（实验日志；关闭时状态镜像）

- `poc/<topic>/NOTES.md` 为粗粒度实验日志，**MUST NOT** 当作 stable must 源。
- 当 `TOPIC.md` `status` 变为 `promoted` 或 `rejected`（主题关闭）且 NOTES 存在时，MUST
  在文件头（blockquote 或首节）写入与 TOPIC **同枚举**的 status，并注关闭日期、方式
  （promote|reject）及 DEC/提案指针（若有）。推荐：`> status: promoted|rejected`。
- **partial** promote 且 TOPIC 仍 `exploring`：NOTES SHOULD 标明 partial / 未全关，
  MUST NOT 仅写 `promoted` 以致误读为全主题关闭。
- 无 NOTES.md 时本条为 N/A（不强制创建）。

### 有条件并行（探索表面）

- **Trunk 时间线线性**：唯一现行实现由 promote/partial 推进。
- **POC 主题有条件并行**：两主题 `explore_surface` 交集为空时 MAY 并行；交集非空时 MUST
  **串行**（`depends_on_topics` 或等待对方 close）或声明 **`conflicts_with_topics`**。
- MUST NOT 将多主题 Δ 性能默认可加；跨主题结论 MUST 在同一 `baseline_trunk_sha` +
  同一 `baseline_protocol` 下重测，或引用冲突 DEC。
- 开题前 MUST 扫描活跃 exploring 的 `explore_surface`（见 [[BEH-018]] 第 9 条）。

### 基线 stale 与重测

- Promote 或 **partial** 推进 Trunk 后：受影响 exploring（**含未关闭的本主题**）MUST
  `baseline_status=stale`。表面不相交的兄弟 MAY 在 close plan 勾 N/A并注明理由。
- 继续测量前若 `stale` 或 `baseline_trunk_sha` 与现行相关 Trunk 不一致：MUST **重测 R0**
  并更新 SHA/`current`，或 evidence 显式 `vs_trunk=<old>` 且 MUST NOT 当作现行 Trunk 基线叙事。
- Partial promote 不创造「半新基线」：禁止用合入前 R0 报相对合入后 Trunk 的加速比。

### 探索延长与主题边界

- 同一假设与同一 `baseline_protocol` 下的深入（含对话延长需求）MUST 留在同一主题：
  追加 evidence、`amend` 提案、可选 partial promote。
- 假设或验收面分叉时 MUST 新建平级 `poc/<other-topic>/`，并用 `depends_on_topics[]`
  声明依赖；各自主题独立 promote/reject。
- MUST NOT 嵌套「子 POC」目录，也 MUST NOT 将子主题「晋升」进父 POC 目录。
  Promote 目标仅为 Trunk（[[BEH-019]]）。
- 欲同时 promote 两 `explore_surface` 相交主题：MUST NOT；先串行或先冲突闭环。

### 关闭后重启（平级新 topic）

- 当 `TOPIC.md` `status` ∈ {`rejected`, `promoted`}（主题已关闭）时：MUST NOT 将该
  `topic_id` 的 status 改回 `exploring` 或 `blocked`（禁止同 topic 重开）。
- 依赖工作就绪后欲再试同一方向：MUST 新建平级 `poc/<new-topic>/`，且：
  - `depends_on_topics` MUST 含已关闭的旧 `topic_id`；若另有使能依赖主题，MUST 一并列出
  - TOPIC（及存在时的 NOTES）MUST 写明相对旧 DEC / `Rejects:` 的**新假设或新 Trunk 前提**；
    MUST NOT 假装旧负结果未发生
  - MUST 新建装订器；首次 R0 后 MUST 写本主题 `baseline_trunk_sha` 与
    `baseline_status=current`
  - 开题 MUST 扫活跃 exploring 的 `explore_surface`（[[BEH-018]] 第 9 条）
- 仍为 `exploring` / `blocked`（含 **partial** promote 未全关）：继续同主题 amend /
  重测 R0（见「基线 stale」）；**不是**本小节「重启」。
- MUST NOT 将 `spec/archive/YYYY-MM/poc-<old>/` 迁回 `poc/<old>/` 冒充新开题；新题 MAY
  只读引用归档路径作为历史证据指针。

### COMMITS.md

凡修改该主题**代码或验证脚本**的 git commit，MUST 追加一行：

| date | code_commit | ndf_commit | proposals | clauses | protocol | note |

纯文档 typo 可免。目标：仅凭 TOPIC + COMMITS 即可回答「依赖哪些提案、用何协议、对哪次代码」。

### Git trailers

POC / promote / 负结果相关 commit message MUST 含：

```text
Topic: <topic>
Proposals: <id>[, ...]
Clauses: <id>[, ...]
```

promote 另加 `Promotes: <topic>`；负结果 DEC 相关 commit 加 `Rejects: <topic>`。
缺 `Topic:` 的 POC 代码提交，审查清单 MUST 判不合格（人工；hook 可选）。

### 与 Trunk SoT

装订器 **MUST NOT** 成为 `status=stable` must 源。Agent 实现 Trunk 时以 `spec/00–50`
为准；装订器仅服务探索进度与可复现。它在 [[META-008]] 中呈现 Design / Implementation /
Test 空间的 POC 工作副本，交互编排不改变其非 SoT 身份。

> rationale: 多轮提案下用主题装订收敛进度，用 ledger/trailer 绑定 commit↔NDF，
> 使「只读文档可复现测量」成为可检查纪律。有条件并行与基线 stale 防止
> Trunk 推进后旧 R0 与默认可加收益。关闭后重启一律平级新 topic，禁止同 id 复活。
> 提案见 `spec/archive/2026-08/proposal-meta-poc-topic-binder.md`、
> `spec/meta/open/proposal-meta-poc-baseline-staleness.md`、
> `spec/meta/open/proposal-meta-poc-sibling-restart.md`。

## NDF 缺陷分类（指针） {#BEH-026}
<!-- ndf: kind=info level=may layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-NDF-GRAPH,CHR-008 -->

维护与修图前 MUST 使用统一缺陷词典：图语义面 / Layer A，与 **绑定溯源面**
（clause↔commit↔装订器↔路径；曾称 Layer B）。
权威定义见 [[DEF-NDF-GRAPH]] 及 [[DEF-NDF-CYCLE]]…[[DEF-NDF-BINDER-DUAL-HEAD]]
（`spec/meta/glossary.md`）；提案 `proposal-meta-ndf-defect-taxonomy`。

图语义面合法性 = NDF 规范锚点 ∧ 图论谓词（\(E_{\mathrm{dep}}\) DAG 等）。  
`ndf_graphcheck` 实现图语义面；`ndf_bindcheck` 实现绑定溯源面且 MUST `depends-on` 本分类。

> rationale: 先定义问题空间，再优化工具 / AI 维护。工具名须表意（bindcheck，非泛称 layerb）。