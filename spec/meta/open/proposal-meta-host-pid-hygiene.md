# Process 提案：宿主 PID / 线程卫生（Chromium cgroup）

> track: process
> Status: Implemented on 2026-08-20
> control-flow: managed
> proposal-id: meta-host-pid-hygiene
> flow-id: meta-host-pid-hygiene
> 日期: 2026-08-20
> 修改: META-011（宿主卫生短句）；`ndf_workflow_status.py`；`AGENTS.md`；canvas skill
> depends-on: META-011
> 范围: `--serve` 单例 / 线程与 SSE 上限 / cgroup pids 预检 / Agent 不残留 serve
> land-targets: spec/meta/process.md, spec/meta/tools/ndf_workflow_status.py, AGENTS.md, .cursor/skills/ndf-workflow-canvas/*

## 1. 背景

Cursor Agent 的 Shell / ripgrep 跑在 systemd Chromium scope 内。cgroup v2 `pids`
把**线程**计入 `pids.max`。无界 `ThreadingHTTPServer` + 长连接 `GET /api/events`
在多标签 / 重连 / 多实例残留时把 `pids.current` 顶到上限，Agent 全工具
`fork`/`pthread_create` 报 `EAGAIN`。系统 load 仍可很低——这不是整机挂死。

反面路径：把 `TasksMax` 调大、或改 `environment=cloud` 子代理——只藏泄漏或绕开本机 SoT。

## 2. 决策

1. **`--serve` MUST 单例。** lock 文件 `tmp/ndf-commander-serve.lock`（pid+port）；
   端口已被本仓活 serve 占用时 MUST 拒绝第二份并打印现有 URL（exit 2）。
2. **HTTP 线程 MUST 有界。** `daemon_threads=True`；工作线程上限（约 16）；
   SSE 并发封顶（约 2）；SSE 循环 MUST 用短超时探测客户端断开，不得靠无限 `sleep`
   拖死线程。
3. **cgroup 预检。** `host-pids` 子命令报告本进程 cgroup `current/max/free` 与可疑
   `ndf_workflow_status.py` / `:8765` / `qemu-system`。空闲 PID &lt; 512 时
   `--serve` / `action-begin` MUST fail-closed，blocker=`host_pid_exhausted`。
4. **显式清理。** `--kill-stale-serve` 才杀本仓过期 serve；默认只报不杀。
5. **Agent 纪律。** Command Agent MUST NOT 后台残留 `--serve`；日常刷新只
   `snapshot --out`；MUST NOT 默认 `--probe-runtime full`。发现 Agent Shell
   `EAGAIN` 时先 `host-pids`，禁止改云端。

不新增 `META-*` 号；在 [[META-011]] 追加极短宿主卫生句。

## 3. 落地清单

| 路径 | 变更 |
|------|------|
| `spec/meta/tools/ndf_workflow_status.py` | `host-pids`；serve lock；线程/SSE 上限；预检 |
| `spec/meta/tools/test_ndf_workflow_status.py` | 单例 / SSE 收口 / 预检 mock |
| `spec/meta/process.md` [[META-011]] | 宿主卫生短句 |
| `AGENTS.md` | EAGAIN → `host-pids`；禁云端绕开 |
| `.cursor/skills/ndf-workflow-canvas/*` | Agent 不启动/不残留 `--serve` |

## 4. 验收

- 连续两次 `snapshot --serve`：第二次拒绝，第一次仍可用
- 打开/关闭 commander 页后，serve 线程数不随标签次数线性涨
- `pids.current` 接近 `pids.max` 时得到明确 `host_pid_exhausted`
- 不调整 Chromium `TasksMax` 作为主修复
