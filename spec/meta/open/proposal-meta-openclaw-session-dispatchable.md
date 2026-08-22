# Process 提案：OpenClaw gateway 可达 ≠ session 可派发

> track: process
> Status: Implemented on 2026-08-21
> reviewed: 已审核
> control-flow: managed
> proposal-id: meta-openclaw-session-dispatchable
> flow-id: meta-openclaw-session-dispatchable
> 日期: 2026-08-21
> 修改: META-011 薄补丁；`probe_openclaw` / `runtime_status` 三态；control-pack blocker；`dispatch-send` 解析 sessionId；cockpit 只读诊断；tests；AGENTS / tools README
> depends-on: META-011
> 范围: Control 平面 OpenClaw；不写面板改绑 CTA；Canvas MUST NOT 写 AGENTS.md
> land-targets: spec/meta/process.md, spec/meta/tools/ndf_workflow_status.py, spec/meta/tools/ndf_dispatch_send.py, spec/meta/tools/test_ndf_workflow_status.py, spec/meta/tools/test_ndf_dispatch_send.py, spec/meta/cockpit/src/types.ts, spec/meta/cockpit/src/main.tsx, AGENTS.md, spec/meta/tools/README.md, .cursor/skills/ndf-workflow-canvas/openclaw-delegate.md

## 1. 背景

`binder_pipeline` attempt 曾 `safe_to_dispatch=true`（`openclaw health` 可达），
`dispatch-send` 仍 `openclaw_nonzero_exit`：

`Invalid session ID: agent:main:feishu:direct:ou_…`

根因：探测把 **gateway 健康**当成 **session 可派发**。`AGENTS.md` 的
`session_key` 常是路由 key；`openclaw agent --session-id` 需要 store 里的
`sessionId`（典型为 UUID）。面板只展示 reachable + 配置串，没有改绑 CTA，
也没有 `session_dispatchable` 门禁。

## 2. 决策

1. OpenClaw Control runtime MUST 分开三态（探测后）：
   - `gateway_reachable`（现有 `health --json` / `reachable`）
   - `session_configured`（`AGENTS.md` 有非空 session_key）
   - `session_dispatchable`（配置值可解析为合法 `--session-id`）
2. Control pack `safe_to_dispatch` MUST 要求 gateway_reachable **且**
   session_dispatchable。缺配置 → `openclaw_session_unconfigured`；
   有配置但不可派发 → `openclaw_session_invalid`。MUST NOT 仅因 health ok
   就送 worker。
3. 解析规则：读 `openclaw sessions --json`；配置值匹配 `key` 或 `sessionId`
   时取该条 `sessionId`。解析后的 id 若仍像 routing key（含 `:` 且非 UUID）
   → 不可派发。`dispatch-send` MUST 使用解析后的 `sessionId`，不得把未解析
   的 routing key 原样塞给 `--session-id`。
4. Commander 面板 MUST 只读投影三态 +「改 `AGENTS.md` session_key 后点探测」
   引导。MUST NOT 新增面板写 `AGENTS.md` 的 CTA（配置仍只在 AGENTS；工具只读）。
5. 不新增 META 数字号；薄补 [[META-011]]。

## 3. 验收

- health ok + 非法 session_key → control-pack `safe_to_dispatch=false`，
  blocker 含 `openclaw_session_invalid`
- 可解析到 UUID sessionId → dispatchable；dispatch-send 使用该 id
- 面板显示 sessionDispatchable=false 与 AGENTS 修复引导
- `ndf_graphcheck.py --meta` hard_errors=0

## Control receipts

| event | phrase | actor | at | proposal_sha | flow_id | hop | status |
|---|---|---|---|---|---|---|---|
| proposal.confirmed | 已确认 | human | 2026-08-21T21:15:00+03:00 | a3b404717c1416f372400661a952308dc79e7d30bb06f7ad69eaa96d8b4f6cd3 | meta-openclaw-session-dispatchable | confirm_land | valid |
| proposal.reviewed | 已审核 | human | 2026-08-21T21:27:37+03:00 | a3b404717c1416f372400661a952308dc79e7d30bb06f7ad69eaa96d8b4f6cd3 | meta-openclaw-session-dispatchable | review | valid |

Process track 已结束；`validation_status` / `perf_status` = `n/a`。无 Trunk 编译/性能验证。
面板仍无「改绑 session」CTA；修好 `AGENTS.md` session_key 后点探测，再开新的装订器 attempt（勿复用已 failed 的 `b9b43468-…`）。
