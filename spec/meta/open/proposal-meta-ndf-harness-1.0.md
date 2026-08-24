# Process 提案：NDF Portable Harness 1.0 稳定版蒸馏

> track: process
> Status: Implemented on 2026-08-24
> Reviewed: 已审核
> 日期: 2026-08-24
> 修改: `packages/ndf-harness/**`（1.0.0 自包含发行）；`spec/meta/README.md`、
>       `spec/meta/tools/HARNESS.md`（版本导航）；本提案
> depends-on: META-008, META-009, META-010, META-011, META-012, META-014,
>             ADR-META-001, ADR-META-003, ADR-META-004,
>             PROP-META-NDF-PORTABLE-HARNESS
> refines: PROP-META-NDF-PORTABLE-HARNESS
> land_targets: packages/ndf-harness/**, spec/meta/README.md, spec/meta/tools/HARNESS.md
> 范围: 本地已验证工作流单向蒸馏为可安装 1.0.0 package；不同步远程 Harness 仓

## Land notes (2026-08-24)

- `VERSION=1.0.0`；`MANIFEST.json` 132 files；source `783163a3…`
- 唯一入口 `skill/ndf-workflow/`；`install.py` 交付全部 17 个 tools 源码
- 验收：package tests 23/23；scratch dual-track install+verify；tools `--help`；中立性扫描；doc links 0 missing
- process track 已结束（人工口令「已审阅」）；`validation_status` / `perf_status` = `n/a`

## 1. 问题

`packages/ndf-harness` 仍为 **0.2.0**（2026-08-10），滞后于本地文字优先、控制面退役、
双委派、Genesis、Context Compiler、闸漂移 diff 等已验证实践。消费方若按 0.2 装包，
会得到过时 Commander 叙事、残缺 tools、无五句入口，且往往还要回维护仓取 `.py`。

## 2. 决策

### P1 — 1.0.0 自包含源码发行

Package MUST 含：norms、`ndf-workflow` skill 组合、AGENTS、templates、stdlib installer、
**全部运行所需 Python tools 源码**、package-local tests、完整 README/架构文档。  
消费方 MUST NOT 依赖维护仓路径、symlink 或额外下载 tools。

### P2 — 唯一人类入口

公共入口仅为 `ndf-workflow`（五句：初始化项目 / 提交Idea / 派发 / 继续 / 关闭）。  
`init/adopt/govern/sync` 降为内部模块；adapters 只装短 wrapper。

### P3 — 单向蒸馏 + 去产品化

本地 `spec/meta/` + skill + tools → 泛化 → package。禁止产品名、topic 专名、SLA 数字、
session ID、绝对宿主路径进包。禁止用 package 反推纠正本地 SoT。

### P4 — 成功合同与退休表面

成功 = 磁盘 `ndf-agent-completion/v1`。Commander / Canvas / Episode / Replay 非现行义务；
`ndf_replay` 仅 tombstone。闸 SHA 漂移 MUST 附 slice diff。

### P5 — 兼容

新 topic：`bundle_dispatch`。Legacy 三闸可读；whole-file SHA ≠ review-slice。  
0.2 升级：只读 migration plan；定稿 SoT 不静默覆盖。

## 3. Land targets

| 路径 | 动作 |
|------|------|
| `packages/ndf-harness/**` | 升 `VERSION=1.0.0`；重写 skill/workflow/docs；上库完整 tools；installer；tests；MANIFEST |
| `spec/meta/README.md` | package ≥1.0.0 导航 |
| `spec/meta/tools/HARNESS.md` | 自包含发行说明 + source SHA |

## 4. 验收

见计划「1.0 验收门」：meta graphcheck、scratch 仅凭 package 安装、tools `--help`、
文档链接、中立性/退休扫描、migration 不覆盖定稿。

## 5. 非目标

- 同步/发布远程 NDF-Harness 仓库（另案）
- 改产品 `spec/00–50` 检索行为
- 把本仓 Feishu/ACP session 绑定打进 package

## Control receipts

| event | phrase | actor | at | proposal_sha | flow_id | hop | status |
|---|---|---|---|---|---|---|---|
| proposal.confirmed | 已确认 | human | 2026-08-24T16:09:00+03:00 | 387446e4adcd313fb5046e2e1bdc746f9fa6c7d3df0adbf0f43d0c8f0b4182ec | meta-ndf-harness-1.0 | confirm_land | valid |
| proposal.reviewed | 已审阅 | human | 2026-08-24T16:26:32+03:00 | 387446e4adcd313fb5046e2e1bdc746f9fa6c7d3df0adbf0f43d0c8f0b4182ec | meta-ndf-harness-1.0 | review | valid |

Process track 已结束；`validation_status` / `perf_status` = `n/a`。无 Trunk 编译/性能验证。
