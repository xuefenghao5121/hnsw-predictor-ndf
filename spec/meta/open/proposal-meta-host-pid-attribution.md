# Process 提案：Host PID 归因拆账 + serve 离开 Chromium

> track: process
> Status: Implemented on 2026-08-21
> control-flow: managed
> proposal-id: meta-host-pid-attribution
> flow-id: meta-host-pid-attribution
> 日期: 2026-08-21
> 修改: META-011（归因 / 拆门槛 / Chromium 拒 serve 短句）；`ndf_workflow_status.py`；tests；AGENTS；canvas skill；tools README
> depends-on: META-011
> 范围: host-pids 拆账；serve vs action-begin 门槛分离；Chromium scope 禁止 `--serve`
> land-targets: spec/meta/process.md, spec/meta/tools/ndf_workflow_status.py, spec/meta/tools/test_ndf_workflow_status.py, AGENTS.md, .cursor/skills/ndf-workflow-canvas/*, spec/meta/tools/README.md

## 1. 背景

[[proposal-meta-host-pid-hygiene]] 已把 NDF `--serve` 封顶到 16 workers / 2 SSE，
并在空闲 &lt; 512 时 fail-closed。该修复**仍然有效**，但不足以解释复发数字：

- NDF serve 理论上最多再占约 18 条线程
- 实测 Chromium cgroup：`current≈34507 max=34550 free≈43`
- `host-pids` 嫌疑只有一个 `--serve` + 诊断命令本身，无 qemu

根因：Cursor Agent / ripgrep / Composer fork 与 Chromium 同属
`app-org.chromium.Chromium-*.scope`。IDE 基线已把 TasksMax 吃到只剩几十；
统一 `HOST_PID_MIN_FREE=512` 把「正常忙的 IDE」也判成 `host_pid_exhausted`。
另：外终端 `host-pids` 看 self cgroup 可能 `headroom_ok`，Composer 仍失败；
live `--serve` 仍可从 Chromium scope 启动并与 IDE 抢预算。

反面路径：调大 TasksMax、改 `environment=cloud`、重跑产品闸门。

## 2. 决策

1. **归因拆账。** `host-pids` MUST 同时报告 self cgroup 与发现的 Chromium app
   slice；输出 top-N 线程消费者与分类计数
   (`chromium_or_cursor` / `ndf_serve` / `ndf_replay_guest` / `qemu` / `other`)。
   当 NDF+qemu 占比很小而 Chromium 接近 max 时，advice MUST 指向关 Cursor 标签 /
   勿从 Composer 起 serve，MUST NOT 默认说「停 leftover serve 就能好」。
2. **拆门槛。** `--serve`（非 Chromium）保留较严余量（512）；`action-begin` 只用
   fork 余量（64），仅在真正将 `EAGAIN` 时 fail-closed（如 free=43）。
3. **Serve 离开 Chromium。** `serve_commander` 若 self 已在
   `app-org.chromium.Chromium-*.scope` MUST 拒绝启动；Command Agent 日常只
   `snapshot --out`；live serve 仅允许仓库外终端。
4. **不调 TasksMax / 不转 cloud。**

不新增 `META-*` 号；在 [[META-011]] 追加短 must 句。

## 3. 落地清单

| 路径 | 变更 |
|------|------|
| `ndf_workflow_status.py` | Chromium 检测；consumers；拆门槛；拒 Chromium serve |
| `test_ndf_workflow_status.py` | 34500/43；advice；Chromium 拒 serve |
| `process.md` [[META-011]] | 归因 / 拆门槛 / 拒 serve 短句 |
| `AGENTS.md` + canvas skill | Composer 只 `--out` |
| tools README | host-pids 字段说明 |

## 4. 验收

- Chromium scope 内 `snapshot --serve` 被拒绝并提示外终端 / `--out`
- `action-begin`：free=400 通过；free=43 仍 `host_pid_exhausted`
- `host-pids` JSON 含 `chromium_cgroup` / `consumers`；NDF 小时 advice 不指向 kill-serve
- 外终端 cgroup 仍允许 `--serve`
- `graphcheck --meta` hard_errors=0
