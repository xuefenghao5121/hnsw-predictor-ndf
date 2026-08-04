# spec/meta/tools — NDF review harness (not product code)

属 NDF **process profile**（[`../README.md`](../README.md)），与产品 `scripts/` **解耦**。
勿再放到仓库根 `tools/`（该目录已删除；审核 harness 只在本目录）。

## 工具分工

| 脚本 | 职责 |
|------|------|
| [`ndf_index.py`](ndf_index.py) | 条款 **索引 / 检索面**：写 `INDEX.md` + `graph.json`；impact / diff / 轻量 dangling / poc-topics |
| [`ndf_graphcheck.py`](ndf_graphcheck.py) | 语义 **图逻辑面**：环、stable must→非 stable、conflicts 非对称、meta 悬空；并渲染 **错误依赖子图** |
| [`ndf_close.py`](ndf_close.py) | POC **回合计划面**：主题关闭时生成往 Trunk 原始 NDF 图追加的清单 + POC 溯源模板 + 强制 post-check（只读 `plan`） |

默认扫描 `spec/meta/` + `spec/00–50`；默认排除 `spec/open/`、`spec/meta/open/`、`spec/archive/`（`--open` / `--archive`，仅 index/graphcheck）。

## 索引（检索）

```bash
python3 spec/meta/tools/ndf_index.py index
python3 spec/meta/tools/ndf_index.py impact BEH-018
python3 spec/meta/tools/ndf_index.py diff HEAD~1
python3 spec/meta/tools/ndf_index.py validate
python3 spec/meta/tools/ndf_index.py poc-topics
```

生成物：`spec/INDEX.md`、`spec/graph.json`（**不是** NDF must 正文）。

## 图逻辑检查（错误 + 子图）

```bash
python3 spec/meta/tools/ndf_graphcheck.py
python3 spec/meta/tools/ndf_graphcheck.py --format text --hop 2
python3 spec/meta/tools/ndf_graphcheck.py --report /tmp/ndf-graphcheck.md
```

硬错误（exit 1）：`cycle`、`stable_dep`、`conflict_asym`、`meta_dangling`。  
Warning（不单独失败）：`unlinked` 孤儿节点。

全文 wiki 断链仍以 `ndf_index.py validate` 为主；`graphcheck` 只检查 **meta 边** 悬空目标。

## POC 回合计划（close plan）

主题结束（promote / reject / partial）时，**先**生成回合计划，再人工改 Trunk 图；计划强调：

1. 只向 Trunk 既有图 **添加/升格** 节点与边（不复制 `poc/*/ndf` 迷你 SoT）
2. 并入散文必须带 `source:` POC 溯源行
3. 落地后 **MUST** 跑 `ndf_index index` + `ndf_graphcheck`

```bash
python3 spec/meta/tools/ndf_close.py plan --topic l4-cache-mgmt --mode partial
python3 spec/meta/tools/ndf_close.py plan --topic io-pipelining --mode promote \
  --report /tmp/close-io-pipelining.md
python3 spec/meta/tools/ndf_close.py plan --topic pq-quality --mode reject
```

`--ids BEH-024 API-012` 可在 `partial`/`promote` 下显式点名回合子集。  
第一版 **无** `apply`（不改 SoT / 不自动归档）。

流程条款正文在 `spec/meta/`；产品行为在 `00–50`。
