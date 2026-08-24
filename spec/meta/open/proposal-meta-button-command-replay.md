# Process 提案：按钮动作 Replay（左右对照）

> track: process
> Status: Implemented on 2026-08-20
> reviewed: 已审核
> 日期: 2026-08-20
> 修改: META-013（Commander Replay = 按钮动作 + 左右 git 对照；旧 Canvas 账本归档）
> depends-on: META-011, META-013, META-015
> 范围: 归档旧 ledger / 自动 commit A→B / Replay UI 左右对照 / command-replay Prompt
> land-targets: spec/meta/process.md；Commander Replay UI；ndf_replay / ndf_actions / skills

## 1. 背景

Command Replay 已收成「查看 / CLI 执行」，但 Commander Replay 页仍保留 Canvas 账本时代的
hop 时间轴、plane×agent 过滤、人话/规范/实发 Prompt 三栏与「查这条账」。目标改为**只回放
前端按钮动作**，用左右 git 对照验证一致性。

## 2. 决策

| 面 | 规则 |
| --- | --- |
| 回放对象 | catalog 按钮（`action_id`）+ git 基线 A + 自动 commit 后的下一 SHA B |
| 左列 | 从 A 开隔离分支/worktree，拷贝原按钮 Prompt 重跑，记录 HEAD |
| 右列 | 对照主线 B（A 的下一记录 SHA），不重跑 skill |
| 旧账本 | `.ndf/replay/canvas-ledger/` 与旧 Episode hop **归档**，MUST NOT 再投影到 Commander |
| 一致性 | 按钮 skill 在刷新 snapshot **前**按 `mayWrite` 自动 `git commit`（`ndf-action: <id>`） |
| 声称 | 页面按钮只生成 instructions Prompt，MUST NOT 宣称「已回放」 |

## 3. [[META-013]] 收窄

Commander Replay 主路径 = 按钮动作列表 + 左右对照。旧 Canvas ledger / hop 归档后不得投影。
`执行回放` / `打开对照` 为 Composer instructions。Agents MUST NOT 跳 Replay。guest-run 仍
CLI 可选（[[META-015]]）。

## 4. 落地摘要

见同日实现：`button-actions` 投影、`action-commit`、Replay UI 重写、旧 ledger 迁
`.ndf/replay/archive/`。
