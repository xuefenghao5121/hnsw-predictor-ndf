# Delegate — Control vs Implementation

| 平面 | 代理 | Pack | 可写 |
|------|------|------|------|
| **NDF Control** | OpenClaw | `control-pack` / `project-control-pack` | `poc/<topic>/ndf/`、`spec/open/`、`spec/meta/open/`、`.openclaw/state.json` |
| **Implementation** | Claude Code ACP | `pack` / `poc-dispatch` / `genesis-pack` | 按 track：`poc/` 或隔离 Trunk；禁越 `allowed_write_root` |

日常 POC 优先 `poc-dispatch … --send`（内联租约）。其它 Control 任务：

```bash
python3 spec/meta/tools/ndf_workflow_status.py control-pack \
  --topic <topic> --task <task> --json
# → 人「派发」/「继续」→
python3 spec/meta/tools/ndf_dispatch_send.py \
  --pack-file tmp/ndf-dispatch-last-pack.json
```

## 成功合同

1. Pack `safe_to_dispatch=true`（否则取消，报告 blockers）
2. 本聊天等人确认「派发」/「继续」（可写 pack 不自动送）
3. `dispatch-send` 送 worker + 心跳等待
4. 读 pack `completion_receipt_path`：**磁盘** `ndf-agent-completion/v1` + closeout succeeded
5. MUST NOT 用手抄 Numbers、transport ACK、stdout JSON 冒充成功

在途问进展 → `dispatch-probe`（探活，不重派）。

## 硬安全门（fail-closed）

错仓库、越界写根、缺人审 bundle、同 topic 并发写 run、上下文漂移、伪造 completion、
ACP 预算溢出、`openclaw_session_invalid`。

握手须含：`repo_root`、`run_id`/`session_id`、`base_sha`、独立 worktree/branch、
`allowed_write_root`。OpenClaw 收到 pack 后更新 `{repo_root}/.openclaw/state.json`。

禁止：Composer 直接 `openclaw.chat_send` 绕过 `dispatch-send`；静默写 `GATES.md`
的 `approved_by`；用 Episode/Replay 当成功条件。
