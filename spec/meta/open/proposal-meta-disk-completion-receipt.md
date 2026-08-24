# Process 提案：dispatch-send stdout 只作完成通知，回执从磁盘读取并补齐握手

> track: process
> Status: Implemented on 2026-08-21
> reviewed: 已审核
> control-flow: managed
> proposal-id: meta-disk-completion-receipt
> flow-id: meta-disk-completion-receipt
> 日期: 2026-08-21
> 修改: META-011 薄补丁；`ndf_dispatch_send.py` 通知/磁盘回执（ACP **与** OpenClaw）；worker 消息；delegate skills；tests
> depends-on: META-011, META-013
> 范围: 所有 `dispatch-send` transactional hop；stdout ≠ 校验回执；磁盘 `ndf-agent-completion/v1` 必须含校验字段（ACP 另含握手）
> land-targets: spec/meta/process.md, spec/meta/tools/ndf_dispatch_send.py, spec/meta/tools/test_ndf_dispatch_send.py, spec/meta/tools/ndf_actions.py, AGENTS.md, .cursor/skills/ndf-workflow-canvas/acp-delegate.md, .cursor/skills/ndf-workflow-canvas/openclaw-delegate.md, spec/meta/tools/README.md

## 1. 背景

`poc-measurement` attempt `ca511456-6886-4bbe-9a2c-c27f0ee65be2`：ACP 运输成功，
`run_sustained` 跑完，Numbers 写进 `poc/hotspot-optimization/ndf/`。收口仍
`failed`。

根因：`dispatch-send` 只从 ACP **stdout** 提取 `ndf-agent-completion/v1`。
Worker 在 stdout 贴了一份薄 JSON（有 `result=success`，无握手/证据列表），
`completion-record` fail-closed。磁盘上另有更完整的
`poc/.../ndf/evidence/poc-measurement-completion.json`，closeout **不读**。
该磁盘文件仍缺 `run_id` / `session_id` / `worktree` / `branch`，且用了
`reproduce` 而非 `reproduce_commands`。

这与「stdout 被截断、模型爱写摘要 JSON」冲突。完整回执应落在 worker 写根内的文件；
stdout 只通知「写完了、去哪读」。

不改产品 SLA，不改装订器三闸口令，不宣称该次测量 hop 已成功。

## 1.1 范围审计（同风险，非测量独有）

bug 在共享入口 `ndf_dispatch_send.py`：`_send_acp` / `_send_openclaw` 都把
stdout **截成末 8000 字符**，再由 `_task_outcome_from_transport` →
`extract_agent_completion` 当校验回执。worker 消息对两种 provider 都写
「Return a completion receipt」。目录里所有 `closeoutPolicy=transactional`
的 hop 都走这条链。

**同一 fail-closed 风险（stdout 薄 JSON / 截断 / 不读盘）：**

| 平面 | catalog id | provider | 额外握手 |
|------|------------|----------|----------|
| 实现 | `poc-measurement` | ACP | `run_id`/`session_id`/`worktree`/`branch` + lease |
| 实现 | `poc-prepare-baseline` | ACP | 同上 |
| 实现 | `poc-isolation-repair` | ACP | 同上 |
| 实现 | `delegate-poc` | ACP | 同上 |
| Control | `new-proposal` | OpenClaw | 无 ACP 握手；仍要 `changed_files` 等 |
| Control | `design-prepare` / `binder-pipeline` / `binder-amend` / `gate-pipeline` | OpenClaw | 同上 |
| Control | genesis（`project_genesis`） | OpenClaw | 同上 |
| Process | `repair-kernel` / `submit-process-improvement` / `land-confirm` / `land-review` | OpenClaw | 同上 |

**本提案明确豁免：**

- `prepare-acp-lease`：`lease_only`，不解析 completion（保持现状）
- `closeoutPolicy=local` 的 snapshot / 诊断 / 打开文件等：无 worker 回执链
- `completion-record` CLI 本身已按**文件路径**校验；坏的是 feeder
- Topics `latest_poc_completion()` **已经扫磁盘** `poc/*/ndf/evidence/*.json`
  做 decision briefing，与 closeout 读 stdout **分裂**；修 dispatch-send 后
  briefing 与收口应对同一份 pack 钉死文件，不得再「面板看见磁盘、收口看 stdout」

历史旁证：`cluster-gbdt` 的磁盘回执已含握手，但仍用 `reproduce` 而非
`reproduce_commands`——字段名漂移是跨 hop 的，不限于测量。

## 2. 决策

1. **Worker stdout MUST 只作完成通知，不得当作校验回执。**
   通知 schema：`ndf-dispatch-notify/v1`，必填
   `result`、`receipt_path`、`topic`、`task`、`episode_id`、`attempt_id`。
   `receipt_path` MUST 为相对 `repo_root` 的路径。
   **ACP 与 OpenClaw 同一合同。** stdout 里即使再出现
   `ndf-agent-completion/v1`，`dispatch-send` MUST NOT 用它做
   `completion-record`。缺通知、多份通知歧义、或 `receipt_path` 非法
   → fail-closed（transport 仍可 `transport_ok`）。
   运输层 MUST NOT 再依赖「末 8000 字符里藏得下完整回执」。

2. **运输结束后，`dispatch-send`（指挥侧工具，非人类二次口令）MUST 读磁盘回执。**
   解析顺序：CLI/ACP 退出 → 提取唯一 notify → 读 `receipt_path` → 校验
   `ndf-agent-completion/v1` → 现有 `completion-record` → action-commit →
   action-finish → `snapshot --out`。
   Command Agent 聊天 MUST NOT 手抄 Numbers / 提案正文冒充 validated success。
   MUST NOT 再等人回复「派发」才去读盘。

3. **`receipt_path` MUST 落在 pack 写根内，且优先用 pack 钉死的路径。**
   Pack MUST 声明 `completion_receipt_path`。默认：
   - 有 topic NDF 目录：`poc/<topic>/ndf/evidence/<task>-completion.json`
   - process / 无 topic：写根内 `tmp/ndf-completion/<attempt_id>.json`
     （仍须落在该 hop 的 `allowed_write_root`）
   Notify 的 path MUST 与 pack 声明相同（规范化后）。路径逃出
   `allowed_write_root` / `repo_root` → fail-closed。
   文件不存在 → `missing_disk_receipt`。失败 hop 若已写回执，仍 MUST 读盘并
   Episode-bind（[[META-011]] 失败 completion 也要绑）。

4. **磁盘回执 MUST 补齐 `completion-record` 必填字段；ACP 另补握手。**
   Worker 写入该文件。两种 provider 都必填：
   `task` / `track` / `base_sha` / `repo_head` / `manifest_sha` /
   `context_plan_sha` / `changed_files` / `changed_file_shas` /
   `reproduce_commands` / `evidence_paths` / `evidence_bundle_sha` /
   `git_commit` / `post_check_receipts` / `result`。
   Claude Code 另加 `worktree` / `branch` / `run_id` / `session_id`。
   OpenClaw Control hop MUST NOT 因缺 ACP 握手而发明 lease；也 MUST NOT
   用 stdout 薄 JSON 混过 `changed_files` 校验。
   字段名 MUST 与 `record_agent_completion` 一致（`reproduce_commands`，
   不得只写 `reproduce`）。
   ACP 握手值 MUST 来自已记录的 runtime lease / ACP resume，与 pack
   `episode_id` / `attempt_id` / `manifest_sha` / `base_sha` 对齐。
   **Dispatcher MUST NOT 伪造 `run_id`、独立 worktree 或 lease。**
   ACP 的 `session_id` MUST 等于本次 `dispatch-send` 使用的 resume id；不一致
   → fail-closed。缺 lease 导致 `missing:active_runtime_lease` 仍 fail-closed
   （本提案不放宽 lease 门禁）。

5. **Worker 消息（ACP 与 OpenClaw）MUST 写明上述合同。**
   ACP：先 `lease-record`（或续接同 attempt 的 active lease），再写实现/测量。
   两种 provider：把完整回执写到 pack 钉死路径，stdout 只输出 notify。
   禁止把薄 completion JSON 当作收口回执。

6. **不新增 META 数字号。** 在 [[META-011]] 把「validated completion」从
   「解析 stdout 唯一 `ndf-agent-completion/v1`」改为
   「notify + 磁盘回执经 `completion-record`」（不限 ACP）。
   `prepare-acp-lease` 保持 `lease_only`。

不在本提案修 `action-commit` 对 `poc/*/ndf/` glob 的 staging（本次
`clean_worktree` 是连带现象，另案）。

## 3. 落地清单

| 路径 | 变更 |
|------|------|
| `spec/meta/process.md` [[META-011]] | 三态第（3）句：notify + 磁盘回执 |
| `spec/meta/tools/ndf_dispatch_send.py` | ACP **与** OpenClaw：抽 notify；读盘；path 绑定；不再用 stdout completion |
| pack 生成（repair/control/project-control） | 写入 `completion_receipt_path` |
| `spec/meta/tools/ndf_actions.py` | wrap / worker 消息：写盘回执 + stdout notify |
| `spec/meta/tools/test_ndf_dispatch_send.py` | ACP 与 OpenClaw 各一条：薄 stdout 失败；磁盘完整回执才 success；path 逃逸 fail |
| `AGENTS.md` / `acp-delegate.md` / `openclaw-delegate.md` / tools README | 指挥层一句 |

## 4. 验收

- ACP 或 OpenClaw exit 0 + stdout 仅薄 `ndf-agent-completion/v1`、无合法 notify → 任务 failed
- 合法 notify + 写根内完整磁盘回执 + `completion-record` valid → 才可 succeeded
- notify path 逃出 `allowed_write_root` → failed，不读该文件
- ACP 磁盘回执缺 `run_id`/`session_id`/`worktree`/`branch` → 仍 failed
- OpenClaw 磁盘回执缺 `changed_files` / `reproduce_commands` → 仍 failed
- `prepare-acp-lease` 仍不要求磁盘 completion
- `ndf_graphcheck.py --meta` hard_errors=0

## Control receipts

| event | phrase | actor | at | proposal_sha | flow_id | hop | status |
|---|---|---|---|---|---|---|---|
| proposal.confirmed | 已确认 | human | 2026-08-21T20:46:00+03:00 | b75883037485e91698be03b358cffb13bfdef51f1aea26f19612b076e04cabdd | meta-disk-completion-receipt | confirm_land | valid |
| proposal.reviewed | 已审核 | human | 2026-08-21T20:53:00+03:00 | b75883037485e91698be03b358cffb13bfdef51f1aea26f19612b076e04cabdd | meta-disk-completion-receipt | review | valid |

Process track 已结束；`validation_status` / `perf_status` = `n/a`。无 Trunk 编译/性能验证。
上次 `poc-measurement` hop 仍是 failed，本审核不把它改写成成功。
