# tools/ndf — README stub

> Status: Draft  
> 与产品 `scripts/` **解耦** 的 NDF 审核 harness。

## 用途
⟨TBD: index / impact / validate / diff⟩

## 命令
```bash
python3 tools/ndf/ndf_index.py index
python3 tools/ndf/ndf_index.py impact ⟨ID⟩
python3 tools/ndf/ndf_index.py diff HEAD~1
python3 tools/ndf/ndf_index.py validate
```

## 生成物
- `spec/INDEX.md` — ⟨TBD⟩
- `spec/graph.json` — ⟨TBD⟩

## 非目标
- 不跑产品 benchmark  
- 不修改 `src/`  
- 不替代 NDF SoT 正文  
