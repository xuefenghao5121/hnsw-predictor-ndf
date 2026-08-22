# Process 提案：ACP 继承指挥官面能力批准（禁止二次人工闸）

> track: process
> Status: Implemented on 2026-08-21
> control-flow: managed
> proposal-id: meta-acp-inherit-capabilities
> flow-id: meta-acp-inherit-capabilities
> 日期: 2026-08-21
> 修改: META-011 薄补丁；dispatch-send ACP argv；worker message；AGENTS；acp-delegate；tests
> depends-on: META-011
> 范围: Cursor 指挥官面是唯一能力人工面；`dispatch-send` 继承已批准能力；禁止在 ACP 会话里再等人点 Bash
> land-targets: spec/meta/process.md, AGENTS.md, spec/meta/tools/ndf_dispatch_send.py, spec/meta/tools/ndf_actions.py, .cursor/skills/ndf-workflow-canvas/acp-delegate.md, spec/meta/tools/test_ndf_dispatch_send.py

## 1. 背景

`poc-measurement` 已在 Cursor 指挥官面走完 `capability-approve`（含
`command_allowlist` / `run_sustained` / `sudo_cgroup`），pack
`safe_to_dispatch=true`。`dispatch-send` 用 `claude --resume -p` 送到 ACP 后，
worker 因 Bash「This command requires approval」fail-close，并把
`execution_binding_stale` 当成测量 blocker。人类被设计成要去 ACP 会话里再批一次。

这与「Cursor 是最终指挥面」冲突。主机 sudo 已免密；NDF 不应再叠一层 ACP 人工闸。

## 2. 决策

1. **能力人工面只有指挥官（Cursor Composer / commander）。**
   `capability-approve` + 本聊天「派发」之后，worker MUST 执行绑定测量/写入。
2. **`dispatch-send` 对 ACP print/resume MUST 继承该批准**：默认 argv 带
   `--permission-mode bypassPermissions` 与 `--dangerously-skip-permissions`。
   MUST NOT 再要求人类在 ACP 会话里点 Bash。`NDF_ACP_DISPATCH_CMD` 覆盖时不改 argv。
3. **Worker 消息 MUST 写明**：指挥官已批准；禁止等 ACP Bash 提示；
   `execution_binding_stale` MUST NOT 当测量 blocker（身份绑定 ≠ 执行 HEAD）。
4. **不新增 META 数字号**；[[META-011]] 追加短 must 句。

不改产品 SLA，不改装订器三闸口令。

## 3. 验收

- `_acp_argv` 在 `execution_capabilities_ready` / `safe_to_dispatch` 时含 bypass 旗标
- worker message 含「指挥官面已批准 / 禁止 ACP 二次批准」
- graphcheck --meta hard_errors=0
