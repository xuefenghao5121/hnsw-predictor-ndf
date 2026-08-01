# Proposal: NDF 条款索引 / impact 审核面

> 日期: 2026-08-01
> track: process
> Status: Implemented on 2026-08-01
> 关联: 人工审核跳转体验；不改变条款 SoT（仍为 Markdown）

## 已落地

| 产物 | 说明 |
|------|------|
| `tools/ndf/ndf_index.py` | `index` / `impact` / `validate` / `diff`（与产品 `scripts/` 解耦） |
| `spec/INDEX.md` | 按前缀可点进 `{file}#{ID}`（生成物） |
| `spec/graph.json` | 节点 + edges + backlinks |
| `skills/ndf-workflow/SKILL.md` | 对齐 AGENTS 双轨 |

默认扫描排除 `spec/open/` 与 `spec/archive/`（避免提案草稿撞 ID）；`--open` / `--archive` 可打开。
