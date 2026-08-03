# Phase C 摘要 — NDF hygiene verification / L2

> 日期: 2026-07-31
> 说明: ACP 会话 `d21779ab-…` resume 不可用且 skip-permissions 委派被拦截；本摘要由仓库内直接完成阶段 C 后生成。

## 改动文件

| 文件 | 变更 |
|------|------|
| `spec/50-verification/acceptance.md` | OBS-* → BEH-*；冷 I/O 补 VER-021/022/024/025；VER-030 双轨对齐 CON-SLA-011；元数据补齐 |
| `spec/50-verification/acceptance-p2.md` | VER 元数据；P2 过渡 vs Charter 95% 标注 |
| `spec/20-behavior/*.md` | BEH-003…013 `refines`；禁止 `refines=DEC-*`；BEH-016 元数据 |
| `spec/00-charter/glossary.md` | DEF-012…016（Page Search / DW / FINE_DIRECT / Honest I/O / MemoryMax） |

## must 级 L1 VER 覆盖

| L1 | VER | 状态 |
|----|-----|------|
| BEH-001 | VER-003, VER-035 | 有 |
| BEH-002 | — | **缺口**（搜索模式分支无独立 VER） |
| BEH-009 | VER-002 | 有 |
| BEH-014 | VER-006, VER-022, VER-025 | 有 |
| BEH-016 | VER-021 | 有 |
| CHR-006 / CON-HONEST-002 / CON-SLA-011 | VER-030 | 有 |
| API-004 | — | **缺口**（格式契约靠 BEH-009 间接覆盖） |
| API-005 / API-006 | — | **缺口** |
| CON-SLA-008 | VER-006 / VER-022 | 有（间接） |
| CON-SLA-010 | VER-021 / VER-025 | 有 |

无死 `OBS-*` / 悬空 `DEC-039` 引用于固定目录验证层。
