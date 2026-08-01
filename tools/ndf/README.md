# tools/ndf — NDF review harness (not product code)

与 `scripts/`（数据 pipeline / 训练 / GT）**解耦**。本目录只服务规范审核：

- 条款索引 / 依赖闭包 / 断链检查 / git diff 触及的 ID

```bash
python3 tools/ndf/ndf_index.py index
python3 tools/ndf/ndf_index.py impact BEH-018
python3 tools/ndf/ndf_index.py diff HEAD~1
python3 tools/ndf/ndf_index.py validate
```

生成物写在 `spec/INDEX.md`、`spec/graph.json`（便于在规范树内跳转）；**不是** NDF must 正文。
