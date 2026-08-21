# Process 提案：OpenClaw session_key ≠ agent --session-id

> track: process
> Status: Implemented on 2026-08-21
> reviewed: 已审核
> control-flow: managed
> proposal-id: meta-openclaw-session-key-transport
> flow-id: meta-openclaw-session-key-transport
> 日期: 2026-08-21
> 修改: META-011 / AGENTS 措辞；`resolve_openclaw_dispatch_session`；`_send_openclaw` gateway sessionKey；tests；cockpit/skills 引导
> depends-on: META-011
> 范围: Control OpenClaw transport；保持 AGENTS 飞书 session_key；不改 Canvas 写 AGENTS
> land-targets: spec/meta/process.md, AGENTS.md, spec/meta/tools/ndf_workflow_status.py, spec/meta/tools/ndf_dispatch_send.py, spec/meta/tools/test_ndf_workflow_status.py, spec/meta/tools/test_ndf_dispatch_send.py, spec/meta/tools/README.md, .cursor/skills/ndf-workflow-canvas/openclaw-delegate.md

## 1. 背景

`AGENTS.md` 飞书 `session_key`（`agent:main:feishu:direct:…`）一直适合 MCP
`chat_send`。8/20 `dispatch-send` 误把同一串塞进 `openclaw agent --session-id`
（SAFE_SESSION_ID_RE，禁 `:`）→ `Invalid session ID`。key 未坏；字段用错。

## 2. 决策

1. `session_key` = OpenClaw **路由身份**（可含 `:`）。MUST 保留在 `AGENTS.md`。
2. `openclaw agent --session-id` 仅接受 UUID 类 id；routing key MUST NOT 原样传入。
3. `_send_openclaw`：routing key → `openclaw gateway call agent`，params 含
   `sessionKey` + `idempotencyKey`（与 chat_send 等价入口）；仅当已有 UUID
   `resolved_session_id` 时才用 `agent --session-id`。
4. `session_dispatchable`：gateway 可达且配置值在 `sessions` store 的 `key`（或
   已是合法 UUID）→ 可派发。MUST NOT 仅因 sessionId 非 UUID 判 `openclaw_session_invalid`。
5. 薄补 [[META-011]]；撤回「必须改成 UUID」的错误引导。

## 3. 验收

- 当前飞书 AGENTS key + store 有匹配 key → `session_dispatchable=true`
- `_send_openclaw` 对 routing key 的 argv/params 含 `sessionKey`，不含非法 `--session-id`
- UUID 配置仍走 `--session-id`
- `ndf_graphcheck.py --meta` hard_errors=0

## Control receipts

| event | phrase | actor | at | proposal_sha | flow_id | hop | status |
|---|---|---|---|---|---|---|---|
| proposal.confirmed | 已确认 | human | 2026-08-21T21:33:00+03:00 | 202692d44f276edcc879f4f8afe1b7f3366959e4856cfaa58961ba2aeea32a59 | meta-openclaw-session-key-transport | confirm_land | valid |
| proposal.reviewed | 已审核 | human | 2026-08-21T21:39:23+03:00 | 202692d44f276edcc879f4f8afe1b7f3366959e4856cfaa58961ba2aeea32a59 | meta-openclaw-session-key-transport | review | valid |

Process track 已结束；`validation_status` / `perf_status` = `n/a`。无 Trunk 编译/性能验证。
飞书 `session_key` 保留；探测后可开新的装订器 attempt（勿复用已 failed 的 `b9b43468-…`）。
