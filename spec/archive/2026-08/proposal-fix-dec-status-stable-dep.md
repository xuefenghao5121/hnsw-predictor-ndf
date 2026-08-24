# Proposal: 补齐 DEC status=stable 消除 stable_dep {#PROP-FIX-DEC-STATUS-STABLE-DEP}

> track: bug  
> Status: Implemented on 2026-08-06  
> 日期: 2026-08-06  
> 关联: graphcheck product `stable_dep` ×23  
> 场景: 产品图卫生  
> 原则: 保留结构边；不改 `src/`；Harness / state.json 不动

## 1. 动机

`ndf_graphcheck.py --product` 报 23 条 `stable_dep`：stable must 的
`depends-on` / `refines` / `verifies` 指向 DEC，但目标 DEC 的 `<!-- ndf: -->`
缺 `status=`，被判非 stable。

advise 默认 O1=`remove_edge`。本提案**不采用**：CHR/BEH/CON/VER → DEC 为有意结构边。

## 2. 变更

给下列已采纳产品 DEC 的 ndf 行补 `status=stable`（不改 affects/其余字段）：

| ID | 文件 |
|----|------|
| DEC-017, DEC-021 | `spec/decisions/02-fine-rerank-experiments.md` |
| DEC-034, DEC-035, DEC-037 | `spec/decisions/04-p2.md` |
| DEC-057, DEC-059, DEC-062 | `spec/decisions/05-odirect-floor.md` |
| DEC-065, DEC-067, DEC-068 | `spec/decisions/06-strict-cgroup.md` |

## 3. 非范围

- 15× `unlinked` warning  
- bindcheck（`missing_trailer` / `draft_vs_stable` 等）  
- `packages/ndf-harness/**`、`.openclaw/state.json`

## 4. 验收

`python3 spec/meta/tools/ndf_graphcheck.py --product --report tmp/ndf-graphcheck.md`  
→ **hard_errors=0**（unlinked 警告可仍在）
