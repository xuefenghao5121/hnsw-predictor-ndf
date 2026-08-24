---
name: ndf-workflow
description: >-
  Unique human-facing NDF workflow entry (ADR-META-004): 初始化项目 / 提交Idea /
  派发 / 继续 / 关闭, plus health when asked. Routes internally to modules;
  never asks the user to pick a skill, button, or command.
disable-model-invocation: false
---

# NDF Workflow（唯一人类入口）

## Authority

1. `AGENTS.md`
2. `spec/meta/`（`README.md`、`language.md`、`process.md`、`decisions/`）
3. 产品契约 `spec/00–50`（及产品 `spec/open/`）

**MUST NOT** 用 `packages/ndf-harness/`、`.cursor/skills/ndf-harness/`、或
`spec/meta/cockpit/` / Commander 投影指导本地流程。

## Human cognitive contract

人对齐这五句口令即可（健康诊断另说）：

| 人说 | 内部模块 | 含义 |
|------|----------|------|
| **初始化项目** | [genesis.md](genesis.md) | Project Genesis G0→G3 |
| **提交Idea** / 新需求 | [intake.md](intake.md) → [proposal.md](proposal.md) | 分流写根 + 提案 |
| **派发** | [poc.md](poc.md) / [delegate.md](delegate.md) | 绑定 bundle，送 worker |
| **继续** | [poc.md](poc.md) | 修订装订器，再派发 |
| **关闭** | [close.md](close.md) | promote / partial / reject |
| （询问健康） | [health.md](health.md) | 只读 topic/spec health |

**禁止**：让用户选 skill / 按钮 / CLI 子命令；内部路由，对外只回下一步口令。

## Idea 平面（[[ADR-META-004]]）

| plane | 写根 |
|-------|------|
| product | `spec/open/` |
| process | `spec/meta/open/` |
| mixed | 拆两个互相引用的提案 |
| ambiguous | **先问人**；MUST NOT 默认 poc |

## 硬规则

- **无** Commander / Episode / Replay；历史 `.ndf/replay/` 只读考古
- **成功** = 磁盘 `ndf-agent-completion/v1`（+ closeout succeeded）；transport ACK / stdout ≠ success
- 口令回执写 `GATES.md`（人、时间、内容 SHA）；文件存在 ≠ 已批准

## CLI（Agent 内部）

```bash
# POC 热路径
python3 spec/meta/tools/ndf_workflow_status.py poc-dispatch \
  --topic <topic> --intent implement|measure --send

# Control / Genesis packs
python3 spec/meta/tools/ndf_workflow_status.py control-pack … --json
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack … --json
python3 spec/meta/tools/ndf_workflow_status.py genesis-status --json

# Close（只读 plan）
python3 spec/meta/tools/ndf_close.py plan --topic <topic> --mode promote|partial|reject

# Health（只读）
python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic <topic> --json
python3 spec/meta/tools/ndf_workflow_status.py spec-health --json
```

送 worker：`python3 spec/meta/tools/ndf_dispatch_send.py --pack-file tmp/ndf-dispatch-last-pack.json`
（见 [delegate.md](delegate.md)）。

## Session startup

重读 `AGENTS.md` + 相关 `spec/meta/`；有则读 `MEMORY.md` / `.openclaw/state.json`。
相对路径在 `workspace.repo_root` 下解析。
