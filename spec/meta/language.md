# Meta Language — NDF 条款原始规范（本仓 SoT）

> scope: ndf-process  
> 条款索引: `META-001`, `META-002`, `META-003`, `META-004`  
> **role:** NDF 语言 / 条款格式 SoT（产品无关）  
> 上游参考（**非 SoT**）: [hengliao1972/normative_language](https://github.com/hengliao1972/normative_language)  
> 图语义扩展: [[DEF-NDF-GRAPH]]；取号: [[DEF-META-ID-NS]] / [[ADR-META-002]]

一句话纪律：**散文活在树里，语义活在图里，时间活在 git 里——稳定的条款 ID 是铆钉。**

## NDF 条款书写与元数据 {#META-001}
<!-- ndf: kind=def level=must layer=L0 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=ADR-META-002 -->

本仓 NDF 条款 MUST 使用下列骨架（标题锚点 + 紧随其后的 `<!-- ndf: -->` 行）：

```markdown
## 条款标题 {#«PREFIX-NNN»}
<!-- ndf: kind=<kind> level=<level> layer=<layer> status=<status> since=<version> source=<source> -->
<!-- ndf: refines=<PARENT-ID> depends-on=<DEP-ID> -->

条款正文。强制语气词 MUST / SHOULD / MAY 全部大写。

1. 可测试或可检查条件
2. 用 wiki 交叉引用（形如双方括号包裹的条款 ID；见 META-002）

> rationale: 设计依据（可选）
```

（示例锚点用书名号占位，避免被 `ndf_index` 扫成真实条款；正文里的 wiki 同理用文字描述。）

### 锚点 ID

- 形式：`{#ID}`，ID 匹配 `[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+`（如 `BEH-001`、`CON-SLA-014`、`META-001`、`DEF-NDF-GRAPH`）。
- 全仓（meta + 产品）ID MUST 唯一；process 新号规则见 [[DEF-META-ID-NS]]（wiki；不构成对本条的结构回边）。

### 元数据字段（`<!-- ndf: key=value … -->`）

| 字段 | 要求 | 取值 |
|------|------|------|
| `kind` | SHOULD | `req` / `def` / `arch` / `constraint` / `option` / `verif` / `info` / `decision` |
| `level` | SHOULD | `must` / `should` / `may` / `tbd` |
| `layer` | SHOULD | `L0` / `L1` / `L2` / `L3`（见 [[META-003]]） |
| `status` | SHOULD | `draft` / `stable` / `deprecated`（及工具可识别的扩展） |
| `since` | MAY | 版本或里程碑标签 |
| `source` | MAY | `observed` / `deduced` |
| `scope` | process 条款 MUST | `ndf-process`（正文在 `spec/meta/`） |

同一条款可多行 `<!-- ndf: -->`；边键写在第二行或同行，见 [[META-002]]。

> rationale: 与本仓 `ndf_index` 解析器及既有条款实践对齐；不嵌入具体产品行为。

## NDF 图边与引用 {#META-002}
<!-- ndf: kind=def level=must layer=L0 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-001 -->

### 允许的结构边键（写入 `<!-- ndf: -->`）

仅下列键构成条款图的结构边（扫描仪 MUST NOT 另造边类型）：

`refines`, `depends-on`, `verifies`, `conflicts-with`, `affects`, `superseded-by`, `couples-with`, `model`

- \(E_{\mathrm{dep}}\) := `refines` ∪ `depends-on` — 图论要求见 [[DEF-NDF-GRAPH]]（wiki；图论 SoT 在该条）
- \(E_{\mathrm{conf}}\) := `conflicts-with` — MUST 对称（[[DEF-NDF-CONFLICT-ASYM]]）
- 多目标：逗号分隔 ID 列表

### Wiki 引用

- `[[ID]]` 为正文交叉引用，**不自动**成为结构边，除非另有 `<!-- ndf: depends-on=… -->` 等声明。
- Process 条款 MUST NOT 用结构边指向产品树节点（meta 自洽；见 [[ADR-META-001]] 与去产品交错纪律）。

### 目录角色（语言层）

- Process profile 正文：`spec/meta/`（`scope=ndf-process`）
- 产品行为契约：`spec/00–50` 等
- 纯 process ID MUST NOT 写入产品树 adopted 表冒充产品 must

## 分层与强制语气 {#META-003}
<!-- ndf: kind=def level=must layer=L0 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-001 -->

### 分层（与 `ndf.yaml` `layers:` 一致）

| Layer | 含义 |
|-------|------|
| L0 | 意图 / 原则 |
| L1 | 可验证契约 |
| L2 | 机制 |
| L3 | 可执行 / 参考模型 |

### 强制语气

- **MUST** / **MUST NOT**：规范要求
- **SHOULD** / **SHOULD NOT**：推荐
- **MAY**：允许
- 探索未定级可用 `level=tbd` 或 `status=draft`

### 三栖纪律

| 栖息地 | 承载 |
|--------|------|
| 树（目录 Markdown） | 人类可读散文与条款正文 |
| 图（`{#ID}` + ndf 边） | 可机械检查的语义关系 |
| git | 时间与证据；装订器 ledger / trailer 见 [[DEF-023]] / [[BEH-025]] |

> rationale: 语言层只定义「怎么写 NDF」；双轨/晋升等流程见 [[CHR-008]] / [[BEH-018]]…。

## NDF `model` 边与语义核纪律 {#META-004}
<!-- ndf: kind=def level=must layer=L0 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-002,META-003,ARCH-008 -->

### 目的

`model=` 边指向独立于生产主路径与验收脚手架的**行为预言机**（可重复 L3 语义核）。
默认目录：`spec/models/`（见 [[ARCH-008]]）。

### 与其它原语的分工

| 原语 | 回答 |
|------|------|
| `verifies=`（VER） | 如何证明契约 |
| 实现 + git | 产品实际行为与时间轴 |
| `poc/` + [[DEF-023]] | 探索史与 commit 对照 |
| **`model=`** | 契约应对齐的参考语义 |

### 空槽

无 `model=` 时，L3 可由 VER（及实现）闭合。`spec/models/` 仅边界 README、无金标文件 **合法**。
缺少 `model=` **不是**图语义硬缺陷（扫描仪 MUST NOT 仅因此失败）。

### 启用与触发

1. **触发面**：主题 **promote** 或 **partial** 收口（与 [[BEH-019]] 同闸）MUST 做出语义核决策：
   **要** / **不要** / **延期**。承载面：`ndf_close.py plan` 清单（只读；不自动写盘）。
2. **造核为 MAY**：仅当契约欠定、预期重构或多实现需要对齐时 SHOULD 蒸馏；bug-fix-only 等
   MAY 勾选「不要」并记理由。
3. **时机**：默认在 Trunk 行为已稳定（晋升或紧随）后**抽象**语义核；允许事后另开产品提案补蒸馏。
4. **reject** 收口：不触发造核决策清单。

### 内容与禁止

语义核 SHOULD 只含：启用条件、时机、操作、不变量。  
MUST NOT：把 poc 树、git patch 账本、COMMITS 行迁入 `models/`；MUST NOT 把性能证据表当作金标 must 正文（证据留 DEC/VER）。

### 图论

`model` 为结构边键（[[META-002]]），但 **不属于** \(E_{\mathrm{dep}}\)（`refines` ∪ `depends-on`），
不参与依赖环判定。

> rationale: 预言机与验收、时间轴分离；promote 收口强制**决策**、不强制**交付**，避免空槽焦虑与 patch 污染。
