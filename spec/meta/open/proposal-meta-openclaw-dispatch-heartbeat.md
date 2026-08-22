# Process 提案：OpenClaw dispatch 心跳续等（替代单次固定超时）

> track: process
> Status: Implemented on 2026-08-21
> reviewed: 已审核
> control-flow: managed
> proposal-id: meta-openclaw-dispatch-heartbeat
> flow-id: meta-openclaw-dispatch-heartbeat
> 日期: 2026-08-21
> 修改: META-011 薄补；`ndf_dispatch_send._send_openclaw` 心跳；AGENTS/tools README；tests
> depends-on: META-011
> 范围: OpenClaw Control dispatch 等待策略；不改 session_key 语义
> land-targets: spec/meta/process.md, AGENTS.md, spec/meta/tools/ndf_dispatch_send.py, spec/meta/tools/test_ndf_dispatch_send.py, spec/meta/tools/README.md

## 1. 背景

复杂 binder 等 hop 时 OpenClaw 可持续工作远超 15 分钟，但
`dispatch-send` 对 `gateway call agent --expect-final` 使用固定
`timeout≈NDF_DISPATCH_TIMEOUT_SEC`（默认 900s）。客户端先超时 fail-closed，
gateway 侧 agent 仍在跑 → 指挥面误报失败。

## 2. 决策

1. OpenClaw transport MUST 用心跳等待，不得仅靠单次固定 `--timeout` 判死。
2. 默认：`ping_sec=60`、`stall_sec=900`（连续无进展）、`max_sec=14400`（绝对上限）。
   可用环境变量覆盖：`NDF_OPENCLAW_PING_SEC` / `NDF_OPENCLAW_STALL_SEC` /
   `NDF_OPENCLAW_MAX_SEC`。
3. 进展信号：目标 session 的 `updatedAt` 或 `totalTokens` 前进；或磁盘
   `completion_receipt_path` 已出现合法回执。有进展则刷新 stall 时钟。
4. 心跳期间更新 `tmp/ndf-dispatch-last.json`（`dispatch_state=awaiting_result`，
   附 `openclaw_heartbeat`），供面板/人观察。
5. 连续 stall_sec 无进展 → `openclaw_stalled`；达 max_sec → `openclaw_timeout`。
6. 薄补 [[META-011]]。

## 3. 验收

- mock：tokens 递增时不在 900s 内误杀
- mock：无进展超过 stall_sec → stalled
- mock：达 max_sec → timeout
- `ndf_graphcheck.py --meta` hard_errors=0

## Control receipts

| event | phrase | actor | at | proposal_sha | flow_id | hop | status |
|---|---|---|---|---|---|---|---|
| proposal.confirmed | 已确认 | human | 2026-08-21T22:19:00+03:00 | 3ae9f78d72affeb4166010ae26ebfa4319df125f0a2ded2feeb28e535f9ec7e0 | meta-openclaw-dispatch-heartbeat | confirm_land | valid |
| proposal.reviewed | 已审核 | human | 2026-08-21T22:24:10+03:00 | 3ae9f78d72affeb4166010ae26ebfa4319df125f0a2ded2feeb28e535f9ec7e0 | meta-openclaw-dispatch-heartbeat | review | valid |

Process track 已结束；`validation_status` / `perf_status` = `n/a`。无 Trunk 编译/性能验证。
下次 OpenClaw `dispatch-send` 自动走心跳续等；勿复用已 failed 的 binder attempt。
