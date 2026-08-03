# spec/meta/tools — NDF review harness (not product code)

属 NDF **process profile**（[`../README.md`](../README.md)），与产品 `scripts/` **解耦**。
勿再放到仓库根 `tools/`（该目录已删除；审核 harness 只在本目录）。

- 条款索引 / 依赖闭包 / 断链检查 / git diff 触及的 ID
- 扫描含 `spec/meta/`（process profile）与 `spec/00–50`
- 默认排除 `spec/open/`、`spec/meta/open/`、`spec/archive/`（`--open` / `--archive`）
- INDEX 分 **META** 与 **Product** 两组

```bash
python3 spec/meta/tools/ndf_index.py index
python3 spec/meta/tools/ndf_index.py impact BEH-018
python3 spec/meta/tools/ndf_index.py diff HEAD~1
python3 spec/meta/tools/ndf_index.py validate
python3 spec/meta/tools/ndf_index.py poc-topics
```

生成物写在 `spec/INDEX.md`、`spec/graph.json`（便于在规范树内跳转）；**不是** NDF must 正文。
流程条款正文在 `spec/meta/`；产品行为在 `00–50`。
