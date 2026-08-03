# spec/meta/tools — README stub

> Status: Draft  
> 与产品 `scripts/` **解耦** 的 NDF 审核 harness。

## 用途
⟨TBD: index / impact / validate / diff / poc-topics；扫 `00–50` + `meta/`⟩

## 命令
```bash
python3 spec/meta/tools/ndf_index.py index
python3 spec/meta/tools/ndf_index.py impact ⟨ID⟩
python3 spec/meta/tools/ndf_index.py diff HEAD~1
python3 spec/meta/tools/ndf_index.py validate
python3 spec/meta/tools/ndf_index.py poc-topics
```

## 生成物
- `spec/INDEX.md` — META vs Product 分组  
- `spec/graph.json` — 含 `scope`  

## 非目标
- 不跑产品 benchmark  
- 不修改 `src/`  
- 不替代 NDF SoT 正文（产品 `00–50` + 流程 `meta/`）  
