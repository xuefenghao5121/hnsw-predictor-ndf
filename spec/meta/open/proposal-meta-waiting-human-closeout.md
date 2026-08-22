# Process 提案：waiting_human / 能力批准必须收口投影

> track: process
> Status: Implemented on 2026-08-21
> control-flow: managed
> proposal-id: meta-waiting-human-closeout
> flow-id: meta-waiting-human-closeout
> 日期: 2026-08-21
> 修改: META-011 薄补丁；dispatch closeout；capability-approve；hooks；Composer prompt
> depends-on: META-011
> 范围: waiting_human 不得把 action-begin 留成 refresh_in_progress；人类能力批准自动 snapshot --out
> land-targets: spec/meta/process.md, spec/meta/tools/ndf_workflow_status.py, spec/meta/tools/ndf_dispatch_send.py, spec/meta/tools/ndf_actions.py, .cursor/hooks/ndf-dispatch-after-pack.sh, .cursor/hooks/ndf-action-commit-snapshot.sh, AGENTS.md, spec/meta/tools/README.md

## 1. 背景

hotspot `poc-measurement`（2026-08-21）：Command Agent `action-begin` 后 pack 停在
`waiting_human`。hook 遇到「writable pack requires explicit Replay Episode」错误 JSON
无法关联 attempt，stop hook 只 `action-commit` 不 `action-finish`。投影停在
`refresh_in_progress`，补测 / 写 DELTA fail-closed。人类批准能力后只手写
`tmp/ndf-capability-receipt.json`，没有 `snapshot --out`，live `--serve` 看不到变化。

这与 [[META-011]]「操作成功或失败后重算完整 snapshot」以及「日常刷新只用
`snapshot --out`」已经矛盾；不需要重启 serve。

## 2. 决策

1. **waiting_human 是终态 closeout。** 未 `safe_to_dispatch` 时 MUST
   `action-finish cancelled` + `snapshot --out --topic`；不得把 started 回执留着。
2. **能力批准是 META hop。** `capability-approve` 写回执、收口 matching started
   attempt、立即 snapshot。MUST NOT 只手改 JSON，MUST NOT 存密码。
3. **hook 关联。** pack 错误 JSON 仍按 CLI `--task` / `--action-id` 关联 started
   receipt。stop hook 在非 in-flight 时 finish+snapshot，不再只 commit。
4. **unsafe pack 不因缺 Episode 抛掉 JSON。** `safe_to_dispatch=false` 的
   waiting_human pack 必须返回给 hook。
5. **live serve。** 只重写 `tmp/ndf-canvas-snapshot.json`；SSE 侦听该文件。
   MUST NOT 要求重启 `--serve`。

不新增 `META-*` 数字号。

## 3. 验收

- waiting_human pack 无 `--episode` 仍返回 JSON，不 raise
- blocked/waiting_human closeout 带 action_id 时 finish cancelled 且 snapshot
- `capability-approve` 写回执 + finish + snapshot
- poc-measurement prompt 含 capability-approve 且禁止重启 serve
- graphcheck --meta hard_errors=0
