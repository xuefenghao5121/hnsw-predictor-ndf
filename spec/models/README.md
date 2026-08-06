# NDF L3 reference models

本目录仅承载 **可执行参考模型 / golden**（条款经 `model=` 引用）。

- **SoT 角色**: L3 行为金标（见 NDF `models/` 约定）
- **边界条款**: [`../meta/architecture.md#ARCH-008`](../meta/architecture.md#ARCH-008)（ARCH-008；正文在 process profile）
- **禁止**: 生产路径实验补丁、Fine Rerank 试错、与 Trunk `src/` 并行的 POC 实现；禁止把 COMMITS/patch 账本塞进本目录

探索性工作请使用仓库根目录 [`poc/`](../../poc/README.md)。
算法对照草稿若需要，可放在 `poc-notes/` 子目录，仍不得链入生产二进制。

## 现行金标

| 文件 | ID | 挂接 | 说明 |
|------|-----|------|------|
| [`willneed-readahead.md`](willneed-readahead.md) | [[MODEL-WILLNEED-001]] | [[BEH-024]] `model=` | WILLNEED readahead 语义核（自 DEC-070 promote 蒸馏） |
| [`sustained-query-measurement.md`](sustained-query-measurement.md) | [[MODEL-SUSTAINED-001]] | [[BEH-035]] / [[CON-SLA-019]] `model=` | Sustained 查询测量语义核（自 DEC-084 promote 蒸馏） |
