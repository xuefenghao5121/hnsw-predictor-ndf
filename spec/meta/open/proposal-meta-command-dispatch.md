# Process 提案：Command Agent 显式 dispatch-send（去掉 afterShell 自动送）

> track: process
> Status: Implemented on 2026-08-21
> control-flow: managed
> proposal-id: meta-command-dispatch
> flow-id: meta-command-dispatch
> 日期: 2026-08-21
> 修改: META-011 薄补丁；Composer pack_delegate wrap；repair-pack 落盘；stop hook；hooks.json；skills；tests；AGENTS
> depends-on: META-011
> 范围: pack → 人审「派发」→ Command Agent 调 dispatch-send；不依赖 afterShellExecution
> land-targets: spec/meta/process.md, AGENTS.md, spec/meta/tools/ndf_actions.py, spec/meta/tools/ndf_workflow_status.py, .cursor/hooks.json, .cursor/hooks/ndf-action-commit-snapshot.sh, .cursor/skills/ndf-workflow-canvas/workflows/poc-measure.md, .cursor/skills/ndf-workflow-canvas/acp-delegate.md, spec/meta/tools/README.md

## 1. 背景

现行设计把「造 pack」与「送 ACP」拆给 Cursor `afterShellExecution`
（`ndf-dispatch-after-pack.sh`）。Composer prompt 要求 Command Agent `repair-pack`
后 STOP，假定 hook 会 `dispatch-send`。在 Cursor Agent 聊天里该 hook **不会跑**；
随后 stop hook 把未送出的 attempt 标成 `cancelled`。没有人把测量交给 Claude Code。

两套隐式派发器（afterShell + stop）抢同一条 attempt，不符合简化。

## 2. 决策

1. **Command Agent 是派发面。** 同一聊天两轮：先 `action-begin` + pack CLI，
   报告 `safe_to_dispatch` / 写根 / episode / blockers，等人回「派发」或「继续」；
   再显式跑 `dispatch-send --pack-file tmp/ndf-dispatch-last-pack.json`。
2. **`dispatch-send` 是唯一送 worker + closeout 入口。** 送 ACP → 等
   `ndf-agent-completion/v1` → `action-commit` → `action-finish` → `snapshot --out`。
   MUST NOT 发明 `openclaw.chat_send`；`dispatch-send` 不是「invent ACP」。
3. **停用 pack 的 afterShell 自动送。** 避免未等人审双发。
4. **stop hook** 对磁盘 ready pack（`safe_to_dispatch` 且 action_id 对齐）记
   `awaiting_human_dispatch`，MUST NOT `cancelled`。
5. **人审短语**是本聊天「派发」/「继续」，不新增 GATES.md / META-010 口令。
6. Command Agent MUST NOT 写 `poc/*/ndf/DELTA.md` / Numbers；worker 写。

不新增 `META-*` 数字号；在 [[META-011]] 追加短 must 句。

## 3. 验收

- pack_delegate prompt 含 `dispatch-send --pack-file`，不含 afterShell 自动送
- `repair-pack` 写出 `tmp/ndf-dispatch-last-pack.json`
- `close_unsent` 对 ready pack skip
- `.cursor/hooks.json` 无 pack afterShell matcher
- graphcheck --meta hard_errors=0（若适用）
