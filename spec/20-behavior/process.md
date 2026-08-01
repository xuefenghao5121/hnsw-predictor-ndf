# Behavior — 探索轨 / 晋升 / 负结果

> 条款索引: `BEH-018`, `BEH-019`, `BEH-020`
> 章程: [[CHR-008]]；目录边界: [[ARCH-008]]；SLA 隔离: [[CON-POC-001]]

## 探索期 NDF 纪律 {#BEH-018}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.7 source=deduced -->
<!-- ndf: refines=CHR-008 depends-on=ARCH-008,DEF-020 -->

当某方向仍在探索轨时：

1. 契约草稿 MUST 留在 `spec/open/proposal-*.md`，或固定目录中显式 `status=draft` / `level=tbd`
2. MUST NOT 将探索期指标写入 `status=stable` 的 `{#CON-SLA-*}` must 行
3. MUST NOT 将探索期行为标为生产默认（环境变量默认开启、去掉 opt-in 门控等）
4. 正文与提案 MUST 使用明确标记：`POC` / `status=draft` / `explore=`，并 `depends-on`
   对应开放提案或 DEC 方向
5. 多轮深入（v1→v2→…）MUST 在**同一探索主题**下追加证据，优先改 `poc/<topic>/` 与提案，
   而不是反复改写 Trunk 的 stable 条款

> rationale: 过早把探索写进 Trunk stable，是 NDF/`src/` 漂移的主因（见 [[DEC-061]]）。

## 晋升闸门 {#BEH-019}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.7 source=deduced -->
<!-- ndf: refines=CHR-008 depends-on=DEF-021,CON-HONEST-002 -->

晋升到 Trunk MUST 同时满足：

1. **证据**：至少一组与目标协议一致的测量（诚实 O_DIRECT 须对齐 [[CON-HONEST-002]]）
2. **提案**：`proposal-*` 经人工确认；固定目录条款从 draft→stable（或新增 stable）
3. **代码**：以**干净合入**方式进入 `src/`（重写/cherry-pick 最小切片），
   commit message 引用条款 ID 与提案/DEC
4. **验证**：触发编译验证与相关 SLA/VER；失败则不得宣称已晋升

禁止：先合主线再补 stable 契约；或先写 stable must 再补 POC 证据。

## 负结果与回退 {#BEH-020}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.7 source=deduced -->
<!-- ndf: refines=CHR-008 depends-on=DEC-061 -->

当探索证伪（样板：[[DEC-061]]）时 MUST：

1. 写/更新 `decisions/`（负结果、根因、废弃条款列表）
2. 将相关 draft/stable 探索条款标 `deprecated` 或移出 must；关闭 `open/proposal-*` 为
   Rejected/Superseded
3. **Trunk `src/`**：删除或永不合并该 POC 表面；若曾误合入，用显式 revert commit（引用 DEC）
4. **`poc/<topic>/`**：可保留失败复现至下一归档周期，或迁入 `spec/archive/` 说明；
   MUST NOT 继续作为生产依赖
5. MUST NOT 要求改写已推送的探索 commit 历史来「对齐文档」——以 DEC + 当前树为准
