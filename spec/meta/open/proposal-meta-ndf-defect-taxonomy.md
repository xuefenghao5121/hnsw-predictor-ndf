# Proposal: NDF 跨层缺陷分类（规范锚点 + 图论判定） {#PROP-META-NDF-DEFECT-TAXONOMY}

> track: process  
> Status: Implemented on 2026-08-04  
> 日期: 2026-08-04  
> 关联: [[CHR-008]], [[BEH-018]], [[BEH-019]], [[BEH-020]], [[BEH-025]], [[BEH-026]], [[DEF-022]], [[DEF-023]], [[DEF-NDF-GRAPH]], [[ARCH-008]], [[CON-POC-001]], [[ADR-META-001]], [[DEC-HYGIENE-001]]  
> 场景: 规范卫生 / 问题空间定义（先定义，后扫描仪）  
> scope: ndf-process

## 1. 动机

在 AI/人工维护 DiskHNSW NDF 之前，必须先固定**问题空间**：什么算条款图缺陷、什么算代码↔规范跨层漂移、如何用数学图论与 NDF 既有概念判定——而不是启发式「看起来不对」。

本提案 **只定义**；不实现新扫描器。后续 harness 提案 MUST `depends-on` 本分类，且 Layer A 算法不得偏离下文点名的图论方法。

## 2. 决策摘要

1. 采用 **两层缺陷空间**：图语义面 / Layer A（条款语义图）+ **绑定溯源面**（曾称 Layer B：clause↔commit↔装订器↔路径）。
2. Layer A 合法性 = **NDF 语义图** ∧ **图论谓词**（DAG / 对称 / 标签约束等）。
3. 绑定溯源面能形式化的给关联谓词；不能硬套图论的标明「非图论」，防伪形式化。
4. 缺陷词汇落在 NDF 已有概念上（条款 ID、status、meta 边、双轨、装订器、ledger）；**禁止**另造边类型。
5. 确认后写入 `spec/meta/glossary.md`（[[DEF-NDF-GRAPH]] 等）及 `process.md` [[BEH-026]] 指针；产品 `00–50` 不写长文。
6. 绑定溯源扫描仪命名为 `ndf_bindcheck`（表意；不用泛称 layerb）。
   **新建**、仅服务 NDF 工作流的 ID（如 `DEF-NDF-*`、`BEH-026`）MUST NOT 在产品树增加 adopted 段（异于历史迁出 ID 的薄指针）。

**落地（2026-08-04）**：glossary DEF 已写入；[[BEH-026]] info 指针已加；本提案 Implemented。  
**矫正（2026-08-04）**：已撤回误加到 `00-charter/glossary.md` / `20-behavior/process.md` 的产品侧 adopted 指针。
---

## 3. NDF 规范锚点（不可省略）

### 3.1 上游 NDF 设计纪律

> 散文活在树里，语义活在图里，时间活在 git 里——**稳定的条款 ID 是把三者铆在一起的铆钉。**

| NDF 概念 | 在本分类中的含义 |
|----------|------------------|
| 散文 / 树 | `spec/**/*.md` 正文与目录；`poc/*/ndf/` 装订器散文 **非** Trunk SoT |
| 语义 / 图 | `{#ID}` 顶点 + `<!-- ndf: refines= depends-on= … -->` 边 |
| 时间 / git | commit、trailers、`COMMITS.md`（[[DEF-023]]） |
| 条款 ID | 唯一铆钉；缺陷报告必须以 ID 寻址；禁止无 ID 口头 must |
| kind / level / layer / status | 节点标签 \(\lambda(v)\) |
| L0–L3 | 不得把无证据的探索写成 stable must（对齐双轨） |

### 3.2 本仓 process SoT

| 条款 | 约束本分类的什么 |
|------|------------------|
| [[CHR-008]] | 探索/晋升双轨；缺陷定义不得鼓励探索期写 Trunk stable |
| [[BEH-018]] | 探索纪律；禁未登记 TOPIC 改 stable |
| [[BEH-019]] | promote：draft→stable 清单、`Promotes:` |
| [[BEH-020]] | reject：DEC、`Rejects:`、deprecated 壳、装订器归档 |
| [[BEH-025]] | 装订器非 SoT；trailers；ledger 行格式 |
| [[DEF-022]] | Topic Binder |
| [[DEF-023]] | Commit Ledger：`code_commit`↔`ndf_commit`↔proposals/clauses/protocol |
| [[ARCH-008]] | `poc/` vs `models/`；装订器非 must 源 |
| [[CON-POC-001]] | POC/evidence 数字不得自动升 production SLA must |
| [[DEC-HYGIENE-001]] | open 卫生；关闭后才回合 |
| [[ADR-META-001]] | 元规范 vs 产品契约分层 |

### 3.3 边键白名单（仅 NDF meta）

与 `ndf_index.EDGE_KEYS` 一致，**禁止**发明非 NDF 边类型：

`refines`, `depends-on`, `verifies`, `conflicts-with`, `affects`, `superseded-by`, `couples-with`, `model`

**划分（本分类）：**

- \(E_{\mathrm{dep}}\) := `refines` ∪ `depends-on`
- \(E_{\mathrm{conf}}\) := `conflicts-with`
- 其余键：默认仅参与**端点完整性**（目标 ID ∈ \(V\)）；是否并入 DAG 由后续扫描仪提案显式声明，默认 **不**并入 \(E_{\mathrm{dep}}\)

---

## 4. 图论基础（在 NDF 边键上建模）

将 Trunk SoT 扫描结果建模为多关系有向图 \(G=(V,E_{\mathrm{rel}})\)：

- \(V\)：条款 ID；标签 \(\lambda(v)\) 含 NDF `status`、`level`
- \(E_{\mathrm{dep}}\)：**MUST 为 DAG**（有向无环）
- \(E_{\mathrm{conf}}\)：**MUST 在无向意义上对称**（若声明 \(u\to v\) 则必须有 \(v\to u\)）

### 4.1 标准算法绑定（实现不得另发明启发式替代）

| 性质 | 图论表述 | 判定算法 | 对齐的 NDF 意图 |
|------|----------|----------|-----------------|
| 无依赖环 | \(G[E_{\mathrm{dep}}]\) 为 DAG | 三色 DFS 找后向边；或 Tarjan / Kosaraju **SCC**（非平凡 SCC 或自环 ⇒ 缺陷） | 语义图无循环定义；可拓扑精化 |
| 依赖可排序 | 存在拓扑序 | Kahn 或 DFS 完成时刻 | 修图建议：父条款先于子条款 |
| 冲突对称 | \(E_{\mathrm{conf}}\) 对称 | 对每条有向声明检查反向 | `conflicts-with` 语义完整 |
| 悬空边 | 边端点 \(\notin V\) | 邻接完整性扫描 | meta / `[[ID]]` 必须可解 |
| 标签约束 | 禁止 \(u\xrightarrow{\mathrm{dep}}v\) 且 \(\lambda(u)=(\mathrm{stable},\mathrm{must})\) 而 \(\lambda(v).\mathrm{status}\neq\mathrm{stable}\) | 边谓词 | 对齐 [[BEH-019]] / [[CON-POC-001]]：stable must 不挂 draft 探索 |
| 孤儿 | 选定边集上 \(\mathrm{deg}^+=\mathrm{deg}^-=0\) | 度统计 | 检索卫生；默认 **warning** |

### 4.2 修图的逻辑合理性

消除 `DEF-NDF-CYCLE` 的补丁 MUST 使 \(E_{\mathrm{dep}}\) 恢复 DAG；宜输出一条合法**拓扑序**供人工监测。禁止：删边后仍非 DAG；或引入新的 stable→非 stable 违规边。

### 4.3 绑定溯源关联结构（二部图，非条款 DAG；曾称 Layer B）

Ledger 可建模为二部图 \(B=(V_{\mathrm{clause}}\cup V_{\mathrm{sha}}, E_{\mathrm{ledger}})\)，边来自 [[DEF-023]] 行（clauses ↔ code_commit / ndf_commit）。度约束用于 `REPRO-BIND-GAP` / `OBS-GRAIN`；**不**要求 git 物理 commit 1:1。扫描仪：`ndf_bindcheck`。

---

## 5. Layer A — 条款语义图缺陷

每条格式：**定义 / 非目标 / 判定 / NDF 锚点 / 是否动代码 / 证据落点**

### 5.1 `DEF-NDF-CYCLE` {#DEF-NDF-CYCLE}

- **定义**：在 \(E_{\mathrm{dep}}\) 上存在有向环（含自环或非平凡 SCC）。
- **非目标**：wiki 正文互指散文；非 `refines`/`depends-on` 的边。
- **判定**：DFS 三色后向边或 SCC；报告环上节点序列。
- **NDF 锚点**：语义图可排序；[[ADR-META-001]] 过程条款互指若成环亦属本缺陷（需修边或降级边类型，不得假装「例外合法环」除非另开 DEC）。
- **是否动代码**：通常 **否**（文档图卫生）。
- **证据**：`ndf_graphcheck` 错误子图；条款 `file:line`。

### 5.2 `DEF-NDF-STABLE-DRAFT` {#DEF-NDF-STABLE-DRAFT}

- **定义**：\(\lambda(u)=(\mathrm{status=stable},\mathrm{level=must})\) 且存在 \(u\xrightarrow{\mathrm{dep}}v\) 使 \(v\) 的 `status` ≠ `stable`（含空）。
- **非目标**：stable/should 或 draft→draft；正文 wiki 引用（非 meta 边）。
- **判定**：遍历 \(E_{\mathrm{dep}}\) + 标签谓词。
- **NDF 锚点**：[[BEH-019]] promote 闸门；[[CON-POC-001]] 探索不升 must。
- **是否动代码**：若升格 \(v\) 为 stable 可能要代码/证据；若改边则文档-only。
- **证据**：graphcheck `stable_dep`；promote 提案 ID 清单。

### 5.3 `DEF-NDF-CONFLICT-ASYM` {#DEF-NDF-CONFLICT-ASYM}

- **定义**：\(u\) 声明 `conflicts-with` \(v\) 但 \(v\) 未反向声明。
- **非目标**：语义上「可能冲突」的散文，无 meta 边。
- **判定**：对称性检查。
- **NDF 锚点**：NDF `conflicts-with` 边语义。
- **是否动代码**：否。
- **证据**：两端条款头。

### 5.4 `DEF-NDF-META-DANGLING` {#DEF-NDF-META-DANGLING}

- **定义**：某 NDF meta 边目标 ID \(\notin V\)。
- **非目标**：全文 `[[ID]]` 断链（归 `ndf_index validate` / wiki dangling）；`model=` 指向路径文件（另议）。
- **判定**：端点完整性。
- **NDF 锚点**：条款 ID 可解；铆钉完整。
- **是否动代码**：否（除非 ID 本应存在于未合并分支——仍先修规范）。
- **证据**：源条款 meta 行。

### 5.5 `DEF-NDF-UNLINKED` {#DEF-NDF-UNLINKED}

- **定义**：在「meta 边 ∪ 正文 wiki refs」导出的无向关联上，入度出度均为 0（实现可与现行 `ndf_graphcheck` unlinked 一致）；排除约定前缀（如纯 ADR 壳）。
- **非目标**：强制每个 glossary DEF 都有边。
- **判定**：度统计；**severity = warning**。
- **NDF 锚点**：检索面卫生。
- **是否动代码**：否。
- **证据**：INDEX / graphcheck warning 列表。

---

## 6. 绑定溯源面 — 跨层缺陷（曾称 Layer B）

### 6.1 `DEF-NDF-SPEC-DRIFT` {#DEF-NDF-SPEC-DRIFT}

- **定义**：实现（`src/` 或已回合路径）已变更，相关 L1 条款节点/边/正文未同步，导致「时间线上代码新、语义图旧」。
- **非目标**：尚未 promote 的 POC 实验与 Trunk stable 不一致（探索轨允许，[[CHR-008]]）。
- **判定**：
  - **可关联化**：变更触达路径集合与条款正文/`model=` 引用的关联缺失或过期（二部/悬挂启发式）。
  - **非图论**：行为是否仍满足 must —— 测试 / 人工 / VER。
- **NDF 锚点**：散文树 vs 语义图 vs git 时间；[[BEH-019]] 合入后契约须对齐。
- **是否动代码**：或改代码回退，或改条款；二者择一并 ledger。
- **证据**：`git` diff、条款 ID、可选 VER。

### 6.2 `DEF-NDF-ZOMBIE-SPEC` {#DEF-NDF-ZOMBIE-SPEC}

- **定义**：条款仍约束或引用已删除/改名的文件、符号、API、env（规范→实现空指）。
- **非目标**：历史 archive 中的故意冻结叙述。
- **判定**：
  - **可关联化**：引用路径/符号作为叶子对实现树做存在性检查（悬挂顶点）。
  - **非图论**：宏/生成代码等需另定抽取规则。
- **NDF 锚点**：实现准绳仍有效；[[BEH-020]] 废弃应留 deprecated 壳而非假活 must。
- **是否动代码**：通常改规范（deprecate/删引用）；偶发恢复代码。
- **证据**：路径/符号列表 + 条款 ID。

### 6.3 `DEF-NDF-REPRO-BIND-GAP` {#DEF-NDF-REPRO-BIND-GAP}

- **定义**：主题相关 code 或 ndf 变更缺少 [[DEF-023]] `COMMITS.md` 行，或缺少 [[BEH-025]] 必需 trailer（`Topic:` / `Proposals:` / `Clauses:`；promote/reject 相应 `Promotes:`/`Rejects:`）。
- **非目标**：纯 typo 文档提交（BEH-025 已允许免 ledger）。
- **判定**：二部关联中应出现的 clause/commit 顶点度为 0；或 trailer 解析失败。
- **NDF 锚点**：[[DEF-023]]、[[BEH-025]]。
- **是否动代码**：否（补 ledger/trailer）；除非补记发现真实未提交变更。
- **证据**：`poc/<topic>/ndf/COMMITS.md`、`git log`。

### 6.4 `DEF-NDF-OBS-GRAIN` {#DEF-NDF-OBS-GRAIN}

- **定义**：ledger/commit 粒度导致无法回答「一次测量依赖哪对 `code_commit`/`ndf_commit`、哪些 proposals/clauses、何种 protocol」（[[DEF-023]] 目标句）。
- **非目标**：强制 git 物理 1:1 commit。
- **判定**：
  - **可关联化**：同一测量协议行关联过多无区分的 SHA（超度）且无 note 可消歧。
  - **非图论**：checklist「仅凭 TOPIC+COMMITS 能否回答」。
- **NDF 锚点**：[[DEF-023]]。
- **是否动代码**：否（拆 ledger 行 / 补 note）。
- **证据**：COMMITS 表。

### 6.5 `DEF-NDF-BINDER-DUAL-HEAD` {#DEF-NDF-BINDER-DUAL-HEAD}

- **定义**：装订器（[[DEF-022]]）中提案/draft 登记与 Trunk 同 ID 的 `status`/`topic=` 不一致，且未按 [[BEH-019]]/[[BEH-020]] 回合或拒绝。
- **非目标**：Trunk 薄 stub 故意指向 archive（已收口）。
- **判定**：同 ID 标签冲突；TOPIC `draft_clauses[]` vs Trunk status。
- **NDF 锚点**：[[BEH-018]]、[[BEH-019]]、[[BEH-025]]、卫生 r2。
- **是否动代码**：视回合而定；纯状态对齐可文档-only。
- **证据**：TOPIC.md、条款头、`ndf_close plan` 报告。

---

## 7. 改图 vs 改代码（NDF 口径）

| 变更性质 | 动作 |
|----------|------|
| 只调整 meta 边 / status 标签，不改变对外 must | 文档-only（仍走提案纪律） |
| 改变 must / API / SLA / 废弃已实现路径 | **必须** 代码变更或显式 deprecate + ledger（[[BEH-019]]/[[BEH-020]]） |
| POC evidence 数字 | **禁止**直接写入 stable must SLA（[[CON-POC-001]]） |

---

## 8. 工具边界

| 工具/表面 | 负责缺陷 | 不负责 |
|-----------|----------|--------|
| `ndf_index` | 检索；轻量 wiki dangling | 绑定溯源面；完整图语义 |
| `ndf_graphcheck` | 图语义面 / Layer A | 绑定溯源；符号存在性 |
| `ndf_bindcheck` | **绑定溯源面**（曾称 Layer B）：bind/dual/grain + 可选 zombie/drift | 图环 / stable→draft 等 Layer A |
| `ndf_close plan` | 回合清单、provenance、提及 ledger checklist | 不替代 bindcheck 门禁 |
| `COMMITS.md` + trailers | 绑定溯源的**人工 SoT**（[[DEF-023]]） | 无则由 bindcheck 报 BIND-GAP |

**判定公式（Layer A）**：缺陷成立 ⟺ **违反 NDF 规范锚点** ∧ **图论谓词失败**。

绑定溯源扫描仪见 `proposal-meta-ndf-bindcheck`；MUST `depends-on` 本文件，并区分「关联谓词」与「非图论语义」。
（工具名用 `ndf_bindcheck`，不用泛称 layerb。）

---

## 9. 变更清单（确认落地时）

| 位置 | 动作 |
|------|------|
| 本文件 | process 提案（Pending → Implemented） |
| `spec/meta/glossary.md` | 增补 DEF-NDF-*（或短名 DEF 指针） |
| `spec/meta/process.md` | 可选：info 段指向本分类 |
| `spec/meta/tools/README.md` | 缺陷分类 SoT 指针 |
| 产品 `00–50` | **不**写入元缺陷长文；**MUST NOT** 为纯 process 新 ID（`DEF-NDF-*`、`BEH-026`）增加 adopted 段 |

## 10. 非目标

- 本提案不实现/重写扫描器、不自动修既有环、不强制 git 1:1  
- 不把元缺陷长文写入产品 `20-behavior/`  

## 11. 验收

- [x] 每类缺陷含：NDF 条款引用、定义、判定（图论或明确非图论）、是否动代码、证据落点  
- [x] 边键仅 NDF meta；\(E_{\mathrm{dep}}\)/\(E_{\mathrm{conf}}\) 划分明确  
- [x] Layer A 算法点名（DFS/SCC/Kahn/对称性）  
- [x] 无新扫描器代码（本提案范围）  
