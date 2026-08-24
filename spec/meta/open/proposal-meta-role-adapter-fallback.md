# Process 提案：角色适配器备选与初始化三角色引导

> track: process
> Status: Implemented on 2026-08-24
> Reviewed: 已审核
> 日期: 2026-08-24
> 修改: [[META-009]]、[[META-011]]；`AGENTS.md`；`.cursor/skills/ndf-workflow/`；
>       `spec/meta/tools/ndf_role_binding.py` 等；`packages/ndf-harness/**`；本提案
> depends-on: META-008, META-009, META-010, META-011, ADR-META-003, ADR-META-004
> refines: META-009, META-011
> land_targets: spec/meta/process.md, AGENTS.md, .cursor/skills/ndf-workflow/**,
>               spec/meta/tools/ndf_role_binding.py, packages/ndf-harness/**
> 范围: 三层解耦为角色绑定；初始化引导配齐指挥面/设计/实现；缺 OpenClaw/Claude 时
>       in_host / dual_session / custom 备选。成功仍只认磁盘 completion。

## Land notes (2026-08-24)

- META-009：闸序含「角色已配置」；`roles_unbound` 挡 G1/派发
- META-011：三角色 + adapter 解析序（CLI → in-host → dual_session → custom）
- `ndf_role_binding.py`；dispatch/status/install 接入；`ndf.workflow.yaml` 角色字段
- skill：`genesis` G-1 向导、`roles/control|implementation`、delegate 按角色
- Harness **1.0.1** + NDF-Harness 仓同步；package tests 25/25
- process track 已结束；`validation_status` / `perf_status` = `n/a`

## 1. 问题

1.0 把三层写成产品名（Cursor / OpenClaw / Claude Code）。缺 CLI 时 dispatch fail-closed，
无合法备选。指挥面宿主多样（Cursor / OpenClaw / Claude / OpenCode / Codex），初始化也不
引导配齐三角色，导致第一次「派发」才突然失败。

## 2. 决策

### P1 — 层 = 角色，产品 = 默认绑定

| 角色 | 职责 | 默认产品绑定（可换） |
|------|------|----------------------|
| Command（指挥面） | 五句口令、造 pack、等人审、调 CLI | 当前宿主 + `ndf-workflow` |
| Control（设计） | 提案、装订器、门禁文档 | OpenClaw |
| Implementation（实现） | POC/Genesis/promote 代码与测量 | Claude Code ACP |

绑定落 `ndf.workflow.yaml` 的 `roles.*`（adapter / fallback / model）。禁止凭据与 session ID。

### P2 — 初始化必须配齐三角色

「初始化项目」在 G0 前（或与 IDEA 并行但须先完成）跑角色向导。人确认后写 yaml；
Genesis `GATES.md` 追加 **「角色已配置」**（人、时间、角色段 SHA）。  
`roles_unbound` → 不得进 G1；`safe_to_dispatch=false`。operational 首次派发若未绑定亦先向导。

### P3 — 解析序（每角色独立）

1. 首选 adapter 且 CLI/会话可用 → 现行路径  
2. `in_host` 或 fallback → 指挥面 spawn 同宿主子 agent（写出 spawn 文件，不伪造 ACK）  
3. `dual_session` → 角色 prompt；人贴两聊天；仍等磁盘回执  
4. `custom` + command → 用户命令  
5. 否则 `role_adapter_unsupported` + `human_next`；不得伪装成功  

禁止指挥面塌缩为「自己写实现/测量」。

### P4 — Workspace 状态泛化

项目本地指挥状态：`ndf.workspace.json` 为首选；`.openclaw/state.json` 作兼容 alias。

## 3. Land targets

| 路径 | 动作 |
|------|------|
| `spec/meta/process.md` | META-009 角色闸；META-011 角色语 + 备选 |
| `AGENTS.md` + skill | 初始化向导；delegate 按角色 |
| `ndf_role_binding.py` + dispatch/status/install | 解析、spawn 文件、roles_unbound |
| `packages/ndf-harness` + NDF-Harness 仓 | 蒸馏同步 |

## 4. 非目标

- yaml 写密钥；指挥面兼做 Control+Implementation；完整各宿主 spawn SDK；恢复面板

## Control receipts

| event | phrase | actor | at | proposal_sha | flow_id | hop | status |
|---|---|---|---|---|---|---|---|
| proposal.confirmed | 已确认 | human | 2026-08-24T16:46:00+03:00 | 39dcb59b415378b24562af9d265a9dc96606b39ac6ecd6059ae89e360759ffca | meta-role-adapter-fallback | confirm_land | valid |
| proposal.reviewed | 已审核 | human | 2026-08-24T17:01:17+03:00 | 39dcb59b415378b24562af9d265a9dc96606b39ac6ecd6059ae89e360759ffca | meta-role-adapter-fallback | review | valid |

Process track 已结束；`validation_status` / `perf_status` = `n/a`。无 Trunk 编译/性能验证。
