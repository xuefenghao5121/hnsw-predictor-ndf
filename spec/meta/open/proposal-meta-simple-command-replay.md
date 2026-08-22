# Process 提案：简化 Command Replay（查看 / CLI 执行）

> track: process
> Status: Implemented on 2026-08-20
> reviewed: 已审核
> 日期: 2026-08-20
> 修改: META-013（Canvas Replay 只查看）；META-015（guest-run 非 Commander 主路径）
> depends-on: META-011, META-013, META-015
> 范围: Command Replay 最短定义 / Agents 与 Replay 解耦 / CLI command-replay
> land-targets: spec/meta/process.md；Commander Agents/Replay UI；ndf_replay.py
> 参考（非 SoT）: docs/ndf-harness-relpay.md

## 1. 背景

本地 Replay 已按 [[META-013]] / [[META-015]] 长成：内容寻址 Episode、R0–R3、guest-run、
Canvas 上 guest-replay 按钮与 Agents→Replay 跳转。对人而言过重，且与
`docs/ndf-harness-relpay.md` 想要的「切片 → 隔离分支重跑 Command → Diff」不对齐。

目标：回放尽量简单、易定义；**Agents 页 MUST NOT 再接入回放界面**。

## 2. 决策：Command Replay 三档

| 模式 | 做什么 | 入口 |
| --- | --- | --- |
| 查看 | 读 Episode：时间、Command、`repo_head`、产出 | Commander **Replay** 页 |
| 验证 | 不建分支、不跑命令；核对记录 SHA / HEAD 可解析 | CLI |
| 执行 | 独立 worktree/分支 `replay/<episode_id>/<timestamp>`，重跑记录 Command，再 `git diff` | CLI |

最短数据面（从现有 Episode commit **投影**，不新建 `.openclaw/episodes/`）：

- `command`（slash / skill / tool 或等价可重放指针）
- `git_snapshot.head_sha` ← 现有 commit `repo_head`
- 文件 before/after SHA（有则投影；缺则报告 coverage gap）

**不采用** Harness 文档中的：`.openclaw/episodes/` 目录、WebSocket、回放结果合并主线、
五色 Diff UI、8080。账本仍在 gitignored `.ndf/replay`。

## 3. 拟改条款

### 3.1 [[META-013]] Canvas 句

将「Canvas Replay 分开呈现 R0/R1/R2/R3；主路径已回放须 guest-proof」收窄为：

- Commander Replay 页 MUST **只查看**（列表 / 查这条账 / 人话与 Prompt 三栏）。
- 「已回放」MUST NOT 由 Commander 页面按钮声称。
- 执行 / 验证 MUST 走 CLI（`command-replay` / 可选 `guest-run`）。
- Agents 页 MUST NOT 跳转 Replay，MUST NOT 提供 `replay-agent-filter` 导航。

R0–R3 等级合同保留在条款中（审计 / 沙盒 / fork），但 **不是** Commander 主交互。

### 3.2 [[META-015]]

- `guest-run` 仍是可选 Lvm 沙盒证明，**不是** Commander 日常回放主路径。
- 默认 Command Replay（CLI `command-replay`）不要求 KVM。
- Canvas MUST NOT 以 hop/prefix guest-replay 按钮作为主入口（删除或 hide）。

## 4. 实现清单（确认后）

1. 落地 §3 到 `spec/meta/process.md`。
2. Commander：Agents 去跳转；Replay 去 guest-replay；保留 `inspect-ledger`。
3. `ndf_replay.py`：`command-replay`、`command-replay-report`（独立 worktree）。
4. 测试 + cockpit build。

## 5. 验收

1. Agents 源码无 `setTab("replay")` / 无 Agents 卡上的 Replay 入口。
2. Replay 页无 `guest-replay-hop` / `guest-replay-prefix`；仍有 `inspect-ledger`。
3. CLI：缺 `repo_head` fail closed；有 SHA 时分支名 `replay/<id>/…`。
4. `ndf_graphcheck.py --meta` hard_errors=0。

## 6. 落地摘要（2026-08-20）

- `spec/meta/process.md`：META-013 / META-015 Canvas vs CLI 分流已写入。
- Commander：Agents 去跳转；Replay 去 guest 按钮；`failClosed: hide`。
- `ndf_replay.py`：`command-replay` / `command-replay-report`。
