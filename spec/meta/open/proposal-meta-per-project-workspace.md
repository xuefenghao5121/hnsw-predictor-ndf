# Process 提案：Per-Project Workspace 绑定

> track: process
> refines: META-011
> depends-on: META-011

## 背景

本地项目管理下，每个仓库维护自己的 `.openclaw/state.json`（gitignore）。OpenClaw 与 Claude Code 的会话是全局的，不会随 Cursor 工作区自动切换。必须每次委派主动携带 `workspace.repo_root`。

## 变更摘要

1. **[[META-011]]** 扩展 Per-Project Workspace：所有 pack 含 workspace；Claude Code worktree 必须在 repo_root 下。
2. **`AGENTS.md`** 双 agent startup 优先 inbound pack 的 repo_root。
3. **`pack` / `genesis-pack`** 补齐 workspace + state_path；handshake 增加 repo_root。
4. **委派模板 / Canvas** 同步 Claude Code 与 OpenClaw 路径传递。

Status: Implemented on 2026-08-12
