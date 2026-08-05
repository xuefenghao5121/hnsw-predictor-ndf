# Meta Process — 探索轨 / 晋升 / 负结果 / 装订

> scope: ndf-process  
> 条款索引: `CHR-008`, `BEH-018`, `BEH-019`, `BEH-020`, `BEH-025`, `BEH-026`  
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
   `spec/meta/open/proposal-meta-*.md`（见 `AGENTS.md` track=process）
2. MUST NOT 将探索期指标写入 `status=stable` 的 `{#CON-SLA-*}` must 行
3. MUST NOT 将探索期行为标为生产默认（环境变量默认开启、去掉 opt-in 门控等）
4. 正文与提案 MUST 使用明确标记：`POC` / `status=draft` / `explore=`，并 `depends-on`
   对应开放提案或 DEC 方向
5. 多轮深入（v1→v2→…）MUST 在**同一探索主题**下追加证据，优先改 `poc/<topic>/`、
   装订器与提案，而不是反复改写 Trunk 的 stable 条款
6. **可执行试错 MUST 落在 `poc/<topic>/`**（或专用 POC 分支）；MUST NOT 在探索期直接
   修改 Trunk `src/` 生产默认路径。若已误改，MUST 按 [[BEH-020]] 或显式 revert /
   迁出到 `poc/`，并做矫正检查（见 `AGENTS.md` §6.2a）
7. MUST NOT 在未登记 `TOPIC.md` 的情况下改写 Trunk `status=stable` 条款「顺便服务某 POC」
8. 探索中发现的 Trunk 缺陷（主线 bug）：默认 MUST 在当前 `poc/<topic>/` 登记为 bug
   切片并修测取证（TOPIC / amend 提案 / COMMITS）；MUST NOT 为「顺便修 bug」绕过本条
   第 6 款直接改生产默认路径。确认合入时 MUST 开产品提案（track=bug 或挂 promote
   干净切片），干净合入 `src/`，并可用 `ndf_close --mode partial` 收口子集而主题继续
   exploring。仅当缺陷已确认与当前假设无关且需紧急修生产路径时，允许 track=bug
   直改 Trunk，事后 MUST 补 DEC/VER。

> rationale: 过早把探索写进 Trunk stable 或直接改 `src/`，是 NDF/`src/` 漂移的主因
> （反面样板见产品负结果 DEC；曾有探索误改 `src/` 后迁 `poc/` 的矫正）。
> 主题装订器提供多提案收敛与 commit 可复现入口，而不引入第二套 must SoT。
> POC 内发现主线 bug 的默认路径见第 8 条。

## 晋升闸门 {#BEH-019}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->
<!-- ndf: refines=CHR-008 depends-on=DEF-021,DEF-022,META-004 -->

晋升到 Trunk MUST 同时满足：

1. **证据**：至少一组与目标协议一致的测量；MUST 对齐产品树现行诚实基准与严格隔离
   验收协议（权威路径：`spec/40-constraints/sla.md`）
2. **提案**：`proposal-*` 经人工确认；固定目录条款从 draft→stable（或新增 stable）；
   promote 提案 MUST 列出 draft→stable ID 清单，并引用该主题 `TOPIC.md`
3. **代码**：以**干净合入**方式进入 `src/`（重写/cherry-pick 最小切片），
   commit message 引用条款 ID 与提案/DEC，并含 trailers：`Topic:`、`Proposals:`、
   `Clauses:`、`Promotes: <topic>`（[[BEH-025]]）
4. **验证**：触发编译验证与相关 SLA/VER；失败则不得宣称已晋升
5. **装订器收口**：`TOPIC.md` status → `promoted`；`COMMITS.md` 记录一对
   `src_commit` + `spec_commit`；装订器迁入 `spec/archive/YYYY-MM/poc-<topic>/`
   或保留摘要指针（二选一，promote 提案写明）
6. **语义核决策**（[[META-004]]）：promote 或 partial 收口 MUST 决定是否蒸馏 L3 语义核
   （**要** / **不要** / **延期**）。造核为 MAY（同提案或紧随产品提案交付 `spec/models/` +
   `model=`）；MUST NOT 用 poc/patch/ledger 冒充金标；**不**替代 VER。
   决策清单承载面：`python3 spec/meta/tools/ndf_close.py plan --mode promote|partial`
   （只读 plan；缺 MODEL 不是工具失败条件）。

禁止：先合主线再补 stable 契约；或先写 stable must 再补 POC 证据。

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
   整包迁入 `spec/archive/YYYY-MM/poc-<topic>/`（防踩坑）；`TOPIC.md` status → `rejected`
5. 仅当条款曾写入 `spec/` draft 时，主线 MUST 保留 `deprecated` 壳并指向归档装订器
6. MUST NOT 要求改写已推送的探索 commit 历史来「对齐文档」——以 DEC + 当前树为准

## POC 主题装订纪律 {#BEH-025}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: refines=BEH-018,ARCH-008 depends-on=DEF-022,DEF-023,CON-POC-001 -->

每个活跃探索主题 `poc/<topic>/` MUST 维护装订器目录：

```text
poc/<topic>/ndf/
  TOPIC.md
  proposals/     # 本主题提案正文，或 stub 指回 spec/open/
  evidence/      # validation / 对照表
  COMMITS.md     # Commit Ledger [[DEF-023]]
```

### 呈现规则（唯一入口与阅读顺序）

- `poc/<topic>/ndf/` MUST 作为 POC 内唯一规范性呈现面；如存在 `poc/<topic>/README.md`，MUST NOT 作为 must 源（仅允许导航指针）。
- 协作者在 POC 内获取 NDF 的推荐阅读顺序 MUST 为：
  1. `poc/<topic>/ndf/TOPIC.md`
  2. `poc/<topic>/ndf/proposals/`（或 stub → `spec/open/`）
  3. `poc/<topic>/ndf/evidence/`
  4. `poc/<topic>/ndf/COMMITS.md`

### TOPIC.md

MUST 记录至少：`topic_id`；`status` ∈ {`exploring`,`blocked`,`promoted`,`rejected`}；
`baseline_protocol`（如产品树现行验收协议路径 + 数据集/线程）；`proposals[]`（路径、Status、
角色 root/amend/process-hygiene）；`draft_clauses[]`；`active_hypothesis` / `next_gate`；
可选 `depends_on_topics[]`。

### 探索延长与主题边界

- 同一假设与同一 `baseline_protocol` 下的深入（含对话延长需求）MUST 留在同一主题：
  追加 evidence、`amend` 提案、可选 partial promote。
- 假设或验收面分叉时 MUST 新建平级 `poc/<other-topic>/`，并用 `depends_on_topics[]`
  声明依赖；各自主题独立 promote/reject。
- MUST NOT 嵌套「子 POC」目录，也 MUST NOT 将子主题「晋升」进父 POC 目录。
  Promote 目标仅为 Trunk（[[BEH-019]]）。

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
为准；装订器仅服务探索进度与可复现。

> rationale: 多轮提案下用主题装订收敛进度，用 ledger/trailer 绑定 commit↔NDF，
> 使「只读文档可复现测量」成为可检查纪律。提案见
> `spec/archive/2026-08/proposal-meta-poc-topic-binder.md`。

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