# Process 提案：Interactive Close Console

> track: process
> Status: Implemented on 2026-08-12
> refines: META-011
> depends-on: META-010,META-011

## 背景

现有 Canvas Close 页只生成一段 Composer prompt，不能在工作台内分步收集 close
意图、展示机械状态或保证每次操作后刷新整个看板。Canvas 本身不是 Agent runtime，
`newComposerChat` 也没有返回回调，因此需要一个不伪造实时对话的交互操作台。

## 变更

1. `ndf_workflow_status.py snapshot` 增加只读 `control.close` 投影。
2. Close 页增加 topic/mode/step/instruction 表单与本地 operation history。
3. Close operation 按步骤路由 OpenClaw / Claude Code，并携带 per-project workspace。
4. 每个 operation prompt MUST 以 `POST_ACTION_SYNC` 结束：重跑 snapshot、更新 Canvas；
   失败保留 blocker，不得把 dispatched 冒充 completed。
5. 人工门禁口令仍由人触发，Canvas MUST NOT 静默批准。

## 非目标

- Canvas 内嵌实时 Agent 流式对话；
- Canvas 直接执行 shell/MCP；
- 将 Canvas/local history 提升为 NDF SoT。
