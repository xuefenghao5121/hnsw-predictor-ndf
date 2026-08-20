# Process 提案：派发结果完整性（transport ≠ task success）

> track: process
> Status: Implemented on 2026-08-20
> control-flow: managed
> proposal-id: meta-dispatch-result-integrity
> flow-id: meta-dispatch-result-integrity
> 日期: 2026-08-20
> 修改: META-011（派发三态短句）；`ndf_workflow_status.py`；`ndf_dispatch_send.py`；tests；tools README
> depends-on: META-011, META-013
> 范围: runtime 投影三态；workspace/handshake/lease 前移；completion 校验；transport 不可冒充成功
> land-targets: spec/meta/process.md, spec/meta/tools/ndf_workflow_status.py, spec/meta/tools/ndf_dispatch_send.py, spec/meta/tools/README.md, AGENTS.md

## 1. 背景

Commander 曾把三层信号混为一谈：

1. **投影**：默认 snapshot 不探测 ACP，却把 `pipeline_reachable=false` 投影成
   `runtime_unavailable`，即使 Claude CLI / OpenClaw gateway 可用。
2. **派发平面**：实现 pack（`claude-code-acp`）与 Control（OpenClaw）正交；OpenClaw
   健康不能清 ACP `runtime_unavailable`。
3. **结果判定**：`dispatch-send` 仅看 CLI exit 0，不解析 Worker 的
   `ndf-agent-completion/v1`；exit 0 + `result=failed` 仍被记为 action success。

反面路径：把 CLI 存在或 gateway `ok` 当成可派发；把 transport acknowledgement 当成
任务成功；跳过 `completion-record` 校验。

## 2. 决策

1. **Runtime 投影 MUST 三态。** `not_probed` | `unavailable` | `reachable`。
   默认 snapshot / `topic_view` 的 `not_probed` MUST NOT 生成 `runtime_unavailable`。
   `repair-pack` / `pack` live probe（full）仍 fail-closed。
2. **Workspace 绑定 MUST 进静态 blocker。** `workspace_truth.workspace_bound=false`
   （repo_head / active_topic 漂移）时 pack MUST NOT `safe_to_dispatch`。
3. **Handshake / lease 声明与校验。** Pack 继续声明 `required_handshake`；
   `dispatch-send` MUST 在发出前核对 pack 侧可验证字段（`base_sha`、`repo_root`、
   `allowed_write_root`、workspace 绑定）。真实 `run_id` / 独立 worktree /
   active lease 仍由 Worker/`lease-record` 产生；dispatcher MUST NOT 伪造
   `run_id` 冒充握手完成。缺可验证字段 → blocked。
4. **Transport ≠ task success。** CLI / openclaw agent exit 0 只表示
   `transport_acknowledged`。MUST 从 stdout 提取**唯一** `ndf-agent-completion/v1`；
   缺失、歧义、`result!=success` → fail-closed，保留 Worker blockers。
5. **Closeout MUST 走 completion 语义。** 失败回执不得 `action-finish --result success`；
   成功路径 SHOULD 调用 `completion-record`（有 episode + 可解析回执时）；校验失败
   MUST NOT 投影 succeeded。

不新增 `META-*` 号；在 [[META-011]] 追加极短派发三态句。

## 3. 落地清单

| 路径 | 变更 |
|------|------|
| `spec/meta/tools/ndf_workflow_status.py` | 投影三态；workspace unbound blocker；pack blockers |
| `spec/meta/tools/ndf_dispatch_send.py` | 解析 completion；transport vs success；closeout |
| `spec/meta/tools/test_ndf_dispatch_send.py` | exit0+failed / 无 receipt / unbound |
| `spec/meta/tools/test_ndf_workflow_status.py` | not_probed 不生成 runtime_unavailable |
| `spec/meta/process.md` [[META-011]] | 派发三态短句 |
| `spec/meta/tools/README.md` | 文档对齐 |
| `AGENTS.md` | 指挥层一句：transport 非任务成功 |

## 4. 验收

- 未 probe：面板/topic_view 不报虚假 `runtime_unavailable`
- workspace unbound：pack `safe_to_dispatch=false`
- CLI exit 0 + failed receipt：dispatch 非零退出，action `failed`，blockers 可见
- 仅 validated success receipt 可投影 succeeded
