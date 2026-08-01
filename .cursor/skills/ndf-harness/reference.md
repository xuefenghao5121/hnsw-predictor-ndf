# Reference — 生成约定

## 路径铁律

1. NDF SoT：`spec/00`…`50`、`spec/decisions/`、`spec/open/`（Pending）  
2. 审核工具：仅 `tools/ndf/`  
3. 产品脚本：仅 `scripts/`  
4. OpenClaw 技能：仓库 `skills/`（非 `.cursor/skills/`）  
5. Cursor 技能：`.cursor/skills/`  

## Stub 标记

- `⟨TBD: …⟩` — 人工必填  
- `Status: Draft` — 未审核  
- `Status: Reviewed` — 人工已过，可作运行提示  

## 与双轨对齐（摘要）

生成任何 OpenClaw/Claude 提示时，必须出现（或引用）下列概念，细节见 `AGENTS.md`：

- `track: poc | promote | process | bug | refactor | rollback`
- 探索 → `poc/` + draft；晋升 → stable + `src/`
- 负结果 → DEC + deprecated（BEH-020）

## 覆盖策略

| 目标文件已存在 | 行为 |
|----------------|------|
| 有人工内容 | 只提议 patch / 并列 `*.stub.md`，不覆盖 |
| 仅有旧 stub | 可刷新骨架，保留已填 `⟨TBD⟩` 答案 |
| 不存在 | 从 `templates/` 复制 |

## 初版生成（人工确认后）

用户说「已确认生成」后，Cursor 才：

1. 将对应 stub 中的 `⟨TBD⟩` 按对话/现有 AGENTS 填成初版  
2. 如需工具：确保 `tools/ndf/ndf_index.py` 可运行  
3. 更新 `MANIFEST.md` 版本表  

## 相关文件

- 产品流程：`AGENTS.md`  
- OpenClaw skill：`skills/ndf-workflow/SKILL.md`  
- Claude：`.claude/CLAUDE.md`  
- 审核工具说明：`tools/ndf/README.md`
