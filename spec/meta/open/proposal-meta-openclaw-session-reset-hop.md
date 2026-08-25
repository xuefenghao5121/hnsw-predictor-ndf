# Process 提案：OpenClaw dispatch 每 hop 先 reset session

> track: process
> status: Implemented
> Status: Implemented on 2026-08-24
> reviewed: 已审核
> plane: process
> control-flow: managed
> proposal-id: meta-openclaw-session-reset-hop
> flow-id: meta-openclaw-session-reset-hop
> 日期: 2026-08-24
> 修改: META-011 薄补；`ndf_dispatch_send._send_openclaw` 在 agent 调用前 `sessions.reset`
> depends-on: META-011
> 范围: OpenClaw Control/Implementation `dispatch-send` 会话寿命；不改 `session_key` 路由身份
> land-targets: spec/meta/process.md, spec/meta/tools/ndf_dispatch_send.py, AGENTS.md, .cursor/skills/ndf-workflow/delegate.md

人类原话：`openclaw把session长对话改为每次reset的短hop`。

## 1. 背景

OpenClaw `dispatch-send` 把每次 hop 接到同一条 Feishu `session_key` 长对话上。
ACP 路径默认 `--fork-session`（`NDF_ACP_FORK_SESSION`，可用 env 关闭），OpenClaw 没有对等行为。

本仓 Genesis 已观测到后果：CHARTER hop 的 transcript 留在同一 session；ARCHITECTURE hop 约 10 分钟后 `FailoverError: LLM request timed out`。pack 已携带本 hop intent + Task Manifest；worker 不需要上一跳对话。

## 2. 决策

薄补 [[META-011]]（不新开 `META-*` 号）：

1. `adapter=openclaw` 的 `dispatch-send` MUST 在发出本 hop agent 消息**之前**，对 pack 的路由 `session_key` 调用 gateway `sessions.reset`（`reason=reset`）。
2. `session_key` 路由身份 MUST 保持不变（`AGENTS.md` 绑定的 Feishu key 不换）。reset 后新的内部 `sessionId` MUST 被下一次 resolve 接受。
3. 默认开启。关闭：`NDF_OPENCLAW_RESET_SESSION=0`（与 `NDF_ACP_FORK_SESSION` 对称）。
4. reset 失败 MUST fail-closed：`openclaw_session_reset_failed`，MUST NOT 把消息送进旧长对话。
5. Command MUST NOT 用 `openclaw.chat_send` 或 MCP `session_reset` 绕过 `dispatch-send`。reset 是 transport 前置步骤，不是成功信号。成功仍只认磁盘 `ndf-agent-completion/v1`。
6. `NDF_OPENCLAW_DISPATCH_CMD` 覆盖路径不自动 reset（测试/override 自负）。

落地位置：`ndf_dispatch_send._send_openclaw`，在构造 `gateway call agent` / `openclaw agent --session-id` 之前。

```text
openclaw gateway call sessions.reset --json --params '{"key":"<session_key>","reason":"reset"}'
```

## 3. 非目标

- 不改 Feishu session_key 绑定
- 不改心跳续等（[[META-011]] 已有 stall/max）
- 不把 reset 当作 completion
- 不在本提案同步 NDF-Harness 上游包
- 不改产品 Trunk / Genesis CHARTER 正文

## 4. 验收

- reset 成功后再发 agent；同一 `session_key` 的 transcript 不含上一 hop
- reset 非 0 退出 → `openclaw_session_reset_failed`，agent 未发送
- `NDF_OPENCLAW_RESET_SESSION=0` 跳过 reset
- `python3 spec/meta/tools/ndf_graphcheck.py --meta` hard_errors=0

## Control receipts

| event | phrase | actor | at | proposal_sha | flow_id | hop | status |
|---|---|---|---|---|---|---|---|
| proposal.confirmed | 已确认 | human | 2026-08-24T16:34:46Z | 01b98f8e79c8c187b0e86b2f3965986e44774556142ab93ae00b230ef0fb97b4 | meta-openclaw-session-reset-hop | confirm_land | valid |
| proposal.reviewed | 已审核 | human | 2026-08-24T17:37:54Z | 01b98f8e79c8c187b0e86b2f3965986e44774556142ab93ae00b230ef0fb97b4 | meta-openclaw-session-reset-hop | review | valid |
