# Proposal: POC 主题装订器与 commit 可复现关联 {#PROP-POC-TOPIC-BINDER}

> track: process
> Status: Implemented on 2026-08-03
> 日期: 2026-08-03
> 关联: [[CHR-008]], [[ARCH-008]], [[BEH-018]], [[BEH-019]], [[BEH-020]], [[CON-POC-001]], [[DEF-020]], [[DEF-021]]
> 场景: 规范卫生 / 双轨可追踪性

## 1. 动机

POC 多轮提案、改测法、加 idea 时，`spec/open/` 与 `NOTES.md` 易漂移；
`.openclaw/state.json` 只能记当前提案。缺**主题级进度入口**时，无法从 NDF 侧复现某次
`poc/` commit 的验证口径与提案依赖。

## 2. 决策摘要

1. 在 `poc/<topic>/ndf/` 维护**主题装订器**（非 Trunk SoT）：`TOPIC.md` + `proposals/` + `evidence/` + `COMMITS.md`
2. 新增 [[BEH-025]]；补丁 [[BEH-018]]/[[BEH-019]]/[[BEH-020]]/[[ARCH-008]]；术语 [[DEF-022]]/[[DEF-023]]
3. POC/promote commit MUST 带 `Topic:` / `Proposals:` / `Clauses:` trailers；`COMMITS.md` 记账
4. promote：装订器归档或标 `promoted`；reject：装订器进 `spec/archive/` + DEC（默认）

## 3. 变更清单

| 位置 | ID | 动作 |
|------|-----|------|
| `meta/process.md`（原 `20-behavior/process.md`） | BEH-025 | 新增主题装订纪律 |
| `meta/process.md` | BEH-018..020 | 补丁引用装订器 |
| `meta/architecture.md` | ARCH-008 | 声明 `poc/*/ndf` |
| `meta/glossary.md` | DEF-022, DEF-023 | Topic Binder / Commit Ledger |
| `AGENTS.md` / `poc/README.md` / `ndf.yaml` | — | 指挥与目录说明 |
| `spec/meta/tools/ndf_index.py` | — | `--poc-topics` |
| 试点 | l4-cache-mgmt, io-pipelining | 建装订器并回填 |
| `meta/`（2026-08-03） | — | 正文迁入 process profile；见 [[ADR-META-001]] |

## 4. 非目标

- `poc/**/ndf` 不作 Trunk must 源
- 不重写历史 commit 补 trailer
- 不强制扩展 `.openclaw/state.json` 主题库
