# Process 提案：OpenClaw Control 委派

> track: process
> refines: META-011
> depends-on: META-010, META-011

## 背景

Topics 工作台在 `legacy_gate_audit` 等 Control 阶段仅提供通用 Composer 聊天，未接通 OpenClaw 的 NDF 文档编排能力。实现派发（Claude Code `pack`）与文档控制流（装订器、GATES 审计、提案）应分流到不同 runtime。

## 变更摘要

1. **[[META-011]]** 增加 OpenClaw Control 委派小节：双 runtime、`control-pack`、写边界、Canvas 路由。
2. **`AGENTS.md`** 增加 `OpenClaw 指挥会话 session_key` 配置；Control vs Implementation 委派分流表。
3. **`ndf_workflow_status.py`** 新增 `control-pack` 子命令；`runtime` 扩展为 control + implementation 双 agent。
4. **Canvas skill** 增加 `openclaw-delegate.md`、Topics Control 动作与 gate 状态表。

## OpenClaw Control 写边界

| 可写 | 禁止 |
|------|------|
| `poc/<topic>/ndf/` | `src/`, `include/`, `tests/` |
| `spec/open/`, `spec/meta/open/` | `spec/meta/` 正文 |
| `.openclaw/state.json` | 静默写 `GATES.md` 的 `approved_by` |

门禁口令仍由人在 OpenClaw 会话发送；Canvas 只发起 audit/draft，不代批。

## control-pack 任务

- `legacy_gate_audit` — 历史 POC 无 GATES 回执时的 gap 报告
- `gate_sha_audit` — receipt SHA vs bundle SHA
- `gate_receipt_draft` — 下一 gate 待审 bundle 摘要
- `binder_amend` — 修订 DESIGN/INTERFACE/PERF_BASELINE
- `control_proposal` — 生成/修订提案

Status: Implemented on 2026-08-12
