# Proposal: Meta 自洽闭环 — 去产品交错 + 工具仅扫 META {#PROP-META-DEPRODUCTIZE-CLAUSES}

> track: process  
> Status: Implemented on 2026-08-05  
> 日期: 2026-08-05  
> 关联: [[ADR-META-001]], [[ADR-META-002]], [[CHR-008]], [[BEH-018]], [[BEH-019]], [[BEH-020]], [[BEH-025]], [[ARCH-008]], [[CON-POC-001]], [[DEF-META-ID-NS]], [[DEF-NDF-GRAPH]]  
> 场景: 规范卫生 / 元分层  
> 原则: meta 图逻辑自洽；ndf 边只指向 meta；检查工具 `--meta` 为门禁

## 1. 动机

1. Meta 条款图挂到产品节点（BEH-019→CON-HONEST-002、BEH-020→DEC-061）并含产品专名。
2. 全仓 `graphcheck` 被产品 `stable_dep` 淹没，无法单独证明 **meta 自洽**。

Meta 是 NDF 元设计核心，\(V_{\mathrm{meta}}\) 上 \(E_{\mathrm{dep}}\) MUST 自洽闭环。

## 2. 决策摘要

### Part A — 去产品交错（仅改 meta 节点）

1. Meta `<!-- ndf: -->` 边 MUST 只指向 meta 命名空间。
2. 产品锚点只许路径/prose，不得进 ndf 边或 must 硬 wiki。
3. 去专名；不换号；**不改任何产品 NDF 节点**。

### Part B — 工具 `--meta`

1. `load_graph(..., meta_only=True)`：仅 `meta/` 或 `scope=ndf-process`。
2. `ndf_index index --meta` → `spec/meta/INDEX.md` + `spec/meta/graph.json`。
3. `validate` / `graphcheck` / `advise --meta`：只在 meta 子图上跑；跨域边呈悬空/硬错误。
4. `bindcheck` / `close` 不加 `--meta`。门禁：`graphcheck --meta` hard_errors=0。

## 3. 变更清单

| 位置 | 动作 |
|------|------|
| `meta/process.md` 等 | Part A scrub（见下表） |
| `meta/tools/ndf_index.py` | `is_meta_clause`、`meta_only`、`--meta` |
| `meta/tools/ndf_graphcheck.py` | `--meta` |
| `meta/tools/ndf_advise.py` | `--meta` |
| `meta/tools/README.md` + `GOVERNANCE.md` | Meta 自洽门禁 |
| `AGENTS.md` | 薄指针 |
| 本文件 | Implemented |

### Part A 细目

| 条款 | 动作 |
|------|------|
| BEH-019 | 去 `CON-HONEST-002` 边；证据改路径 prose |
| BEH-020 | 去 `DEC-061` 边；样板泛化 |
| CHR-008 / BEH-018 / CON-POC-001 / ARCH-008 | 去专名与产品 wiki |
| adr-poc-track | Context 去 DEC-061 wiki |
| adr-ndf-hygiene | Decision 产品数字改路径指针（Context 可留） |

## 4. 验收

```bash
python3 spec/meta/tools/ndf_graphcheck.py --meta   # hard_errors: 0
# 产品 00–50 / decisions 条款 markdown 零 diff
```

## 5. 非目标

- 不改产品 NDF 节点；不批量补 DEC status；不同步 Harness；不改 MEMORY / state.json
