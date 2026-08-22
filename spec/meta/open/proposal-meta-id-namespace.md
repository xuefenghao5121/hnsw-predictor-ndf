# Proposal: Meta 条款独立编号命名空间 {#PROP-META-ID-NAMESPACE}

> track: process  
> Status: Implemented on 2026-08-05  
> 日期: 2026-08-05  
> 关联: [[ADR-META-001]], [[CHR-008]], [[BEH-018]], [[BEH-025]], [[ARCH-008]], [[DEF-020]], [[CON-POC-001]], [[DEF-NDF-GRAPH]]  
> 场景: 规范卫生 / 元分层  
> 修订: 补充 [[ADR-META-001]]「迁入不换号」遗留的编号认知问题

## 1. 动机

[[ADR-META-001]] 将流程条款正文迁入 `spec/meta/`，但 **ID 不换号**，导致 meta 与产品共享
`CHR` / `BEH` / `ARCH` / `DEF` 数字池。观感上像产品续号（如 CHR-008 紧接产品 CHR-007；
产品 BEH-024 与流程 BEH-025 交错），增加误读与取号冲突风险。

已有好先例（应推广为通则）：`CON-POC-001`、`DEF-NDF-*`、`ADR-META-*`、`DEC-HYGIENE-001`。

**本提案不搞全量换号**（引用面过大）；采用「旧号冻结 + 新号独立」。

## 2. 决策摘要

1. **冻结**：下列历史 meta ID **永久保留为 canonical**，MUST NOT 重命名为 `META-*`：
   - `CHR-008`, `BEH-018`…`BEH-026`, `ARCH-008`, `DEF-020`…`DEF-023`
2. **新建 process 条款**（`spec/meta/` 正文）MUST 使用独立命名空间，MUST NOT 再占用产品
   `CHR` / `BEH` / `ARCH` / `DEF` / `CON-SLA` / `CON-00n` 数字续号。
3. **一般流程 must / info**：使用单调序列 **`META-nnn`**，自 **`META-001`** 起编；角色靠
   `<!-- ndf: kind=… layer=… -->` 表达，不再开 `META-BEH-*` / `META-CHR-*` 子号池。
4. **语义前缀并存**（既有惯例继续）：
   - 缺陷词典：`DEF-NDF-*`
   - POC↔SLA 隔离：`CON-POC-*`
   - 流程 ADR：`ADR-META-*` / `ADR-TOPIC-*`
   - 卫生 DEC：`DEC-HYGIENE-*` 等非纯数字产品 DEC 形式
5. **全局唯一**：meta + product 仍共享一张图 / 一个 INDEX；ID 全仓唯一（[[DEF-NDF-GRAPH]]）。
6. **产品取号**：新产品条款继续产品前缀序列；已被 meta 冻结占用的号（如 BEH-018…026、
   CHR-008、ARCH-008、DEF-020…023）视为历史占用，产品 MUST NOT 复用同号。

## 3. 变更清单（确认后落地）

| 位置 | 动作 |
|------|------|
| `spec/meta/decisions/adr-meta-id-namespace.md` | 新增 **[[ADR-META-002]]**（Accepted） |
| `spec/meta/decisions/adr-meta-layer-split.md` | Consequences 追加指针 → ADR-META-002 |
| `spec/meta/glossary.md` | 新增 `{#DEF-META-ID-NS}`：前缀策略短定义 |
| `spec/meta/README.md` | 表格：新条款用 `META-*`；冻结旧号列表 |
| `AGENTS.md` | 薄指针：process 新条款 ID 规则 |
| `spec/ndf.yaml` | `id-prefixes` 增加 `META`；`meta:` 注释/字段说明前缀策略 |
| 本文件 | Pending → Implemented |

**非目标（本轮）**：不改 `CHR-008`/`BEH-018`… 锚点；不改 graphcheck 工具（文档纪律优先）；
不同步 NDF-Harness；不改产品 `BEH-024` 等。

## 4. 拟写入草案（确认后剪切）

### ADR-META-002（摘要）

```text
Decision: 自 2026-08-05 起，新建 ndf-process 条款使用 META-nnn（或既有语义前缀
DEF-NDF-* / CON-POC-* / ADR-META-*）；历史 CHR-008 / BEH-018…026 / ARCH-008 /
DEF-020…023 冻结不换号。Supersedes-in-part ADR-META-001 §Decision.2 的「今后仍与
产品共用数字续号」隐含惯例（路径分层仍以 ADR-META-001 为准）。
```

### DEF-META-ID-NS（摘要）

```text
Process profile 条款 ID 命名空间：新一般条款 META-nnn；语义特例见 DEF-NDF-*、
CON-POC-*、ADR-META-*。冻结列表见 ADR-META-002。
```

## 5. 验收

- [[ADR-META-002]] 可被 wiki 引用；写清冻结列表 + `META-*` + 语义前缀并存
- `ndf.yaml` `id-prefixes` 含 `META`
- `meta/README.md` 与 `AGENTS.md` 有「勿续产品数字」口令
- 抽查：此后 process 提案不得再提议 `BEH-027`（meta）这类产品续号
