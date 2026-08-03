# Validation — DEC-064 memory optimization promote

> date: 2026-08-02
> track: promote
> proposal: `spec/open/proposal-promote-memory-optimization.md`
> decision: [[DEC-064]]
> status: **pass** (retroactive record; fills [[BEH-019]] / AGENTS 场景5 缺口)

## Scope

Trunk 合入切片（VisitedList uint8、adjacency0 streaming free、malloc_trim、upper_vectors swap）。
**不含** pipe_ring_（BEH-021 保持 draft）。

## Build / functional

| 检查 | 结果 |
|------|------|
| Trunk 编译（含 `include/disk_hnsw.h` + `src/core/disk_hnsw.cpp`） | pass（合入 commit `3619013`） |
| SIFT1M recall 回归（POC/同配置对照） | pass — Recall 不变，见 [[DEC-064]] |
| DEEP10M recall | pass — 94.85% 不变 |

## Notes

- 本文件为 promote 后补的场景5记录；数字权威源为 [[DEC-064]] 与 promote 提案。
- 未改 L0/L1 must 契约；无 draft→stable 条款列表。
