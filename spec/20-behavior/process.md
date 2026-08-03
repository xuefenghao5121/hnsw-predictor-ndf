# Behavior — 探索轨 / 晋升 / 负结果

> 条款索引: `BEH-018`, `BEH-019`, `BEH-020`, `BEH-025`
> 章程: [[CHR-008]]；目录边界: [[ARCH-008]]；SLA 隔离: [[CON-POC-001]]
> 术语: [[DEF-020]], [[DEF-021]], [[DEF-022]], [[DEF-023]]

## 探索期 NDF 纪律 {#BEH-018}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.7 source=deduced -->
<!-- ndf: refines=CHR-008 depends-on=ARCH-008,DEF-020,BEH-025 -->

当某方向仍在探索轨时：

1. 契约草稿 MUST 留在 `spec/open/proposal-*.md` 或主题装订器 `poc/<topic>/ndf/proposals/`，
   或固定目录中显式 `status=draft` / `level=tbd`；凡本主题提案 MUST 登记进
   `poc/<topic>/ndf/TOPIC.md`（[[BEH-025]]）
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

> rationale: 过早把探索写进 Trunk stable 或直接改 `src/`，是 NDF/`src/` 漂移的主因
> （样板：[[DEC-061]] Read Coalescing；早期 pipelining 曾误改 `src/` 后迁 `poc/`）。
> 主题装订器提供多提案收敛与 commit 可复现入口，而不引入第二套 must SoT。

## 晋升闸门 {#BEH-019}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.7 source=deduced -->
<!-- ndf: refines=CHR-008 depends-on=DEF-021,DEF-022,CON-HONEST-002,BEH-025 -->

晋升到 Trunk MUST 同时满足：

1. **证据**：至少一组与目标协议一致的测量（诚实 O_DIRECT 须对齐 [[CON-HONEST-002]]；
   现行严格隔离须对齐 [[CON-SLA-014]]）
2. **提案**：`proposal-*` 经人工确认；固定目录条款从 draft→stable（或新增 stable）；
   promote 提案 MUST 列出 draft→stable ID 清单，并引用该主题 `TOPIC.md`
3. **代码**：以**干净合入**方式进入 `src/`（重写/cherry-pick 最小切片），
   commit message 引用条款 ID 与提案/DEC，并含 trailers：`Topic:`、`Proposals:`、
   `Clauses:`、`Promotes: <topic>`（[[BEH-025]]）
4. **验证**：触发编译验证与相关 SLA/VER；失败则不得宣称已晋升
5. **装订器收口**：`TOPIC.md` status → `promoted`；`COMMITS.md` 记录一对
   `src_commit` + `spec_commit`；装订器迁入 `spec/archive/YYYY-MM/poc-<topic>/`
   或保留摘要指针（二选一，promote 提案写明）

禁止：先合主线再补 stable 契约；或先写 stable must 再补 POC 证据。

## 负结果与回退 {#BEH-020}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.7 source=deduced -->
<!-- ndf: refines=CHR-008 depends-on=DEC-061,BEH-025,DEF-022 -->

当探索证伪（样板：[[DEC-061]]）时 MUST：

1. 写/更新 `decisions/`（负结果、根因、废弃条款列表）；DEC 正文或 commit 含
   `Rejects: <topic>`
2. 将相关 draft/stable 探索条款标 `deprecated` 或移出 must；关闭 `open/proposal-*` /
   装订器内提案为 Rejected/Superseded
3. **Trunk `src/`**：删除或永不合并该 POC 表面；若曾误合入，用显式 revert commit（引用 DEC）
4. **`poc/<topic>/`**：可保留失败复现至下一归档周期；**默认**将 `poc/<topic>/ndf/`
   整包迁入 `spec/archive/YYYY-MM/poc-<topic>/`（防踩坑）；`TOPIC.md` status → `rejected`
5. 仅当条款曾写入 `spec/` draft 时，主线 MUST 保留 `deprecated` 壳并指向归档装订器
6. MUST NOT 要求改写已推送的探索 commit 历史来「对齐文档」——以 DEC + 当前树为准

## POC 主题装订纪律 {#BEH-025}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9 source=deduced -->
<!-- ndf: refines=BEH-018,ARCH-008 depends-on=DEF-022,DEF-023,CON-POC-001 -->

每个活跃探索主题 `poc/<topic>/` MUST 维护装订器目录：

```text
poc/<topic>/ndf/
  TOPIC.md
  proposals/     # 本主题提案正文，或 stub 指回 spec/open/
  evidence/      # validation / 对照表
  COMMITS.md     # Commit Ledger [[DEF-023]]
```

### TOPIC.md

MUST 记录至少：`topic_id`；`status` ∈ {`exploring`,`blocked`,`promoted`,`rejected`}；
`baseline_protocol`（如 [[CON-SLA-014]] + 数据集/线程）；`proposals[]`（路径、Status、
角色 root/amend/process-hygiene）；`draft_clauses[]`；`active_hypothesis` / `next_gate`；
可选 `depends_on_topics[]`。

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
> 使「只读文档可复现测量」成为可检查纪律。提案见 `spec/open/proposal-poc-topic-binder.md`。
