# Process 提案：回放沙箱定义与 Guest VM 执行器

> track: process
> Status: Implemented on 2026-08-17
> reviewed: 已审核
> control-flow: managed
> proposal-id: meta-replay-sandbox
> flow-id: meta-replay-sandbox
> 日期: 2026-08-17
> 修改: META-013（R2 adapter / Canvas 指针）；新增 {#META-015}
> depends-on: META-011, META-013
> 范围: 回放执行器边界 / Lsoft·Lns·Lvm / guest-proof / Canvas 宿主只启动 / R2 adapter=bwrap|vm
> land-targets: spec/meta/process.md, AGENTS.md（Replay 段若需对齐）, .cursor/skills/ndf-workflow-canvas/*

## 1. 背景

现行 Canvas「沙箱回放」仍经宿主 `newComposerChat` 执行。提示词标签、
`isolate` worktree、R2 `bwrap` 均在**同一内核、同一用户、同一仓库树**上运行：

- Composer cwd = 现仓，约束无强制力；
- worktree / bwrap 只证明某条 CLI 用了另一棵树或用户命名空间，**不证明执行器无法写现仓**；
- [[META-013]] 已要求：R0/R1 若只能经 Composer 生成指令，MUST 标为 instructions，
  不得显示为 Replay 已执行——当前主按钮仍接近违反该精神。

回放目标不变：恢复已记录状态（人话 / Manifest / Plan / 下达 / 回执），不是重放当时
组装 prompt，也不是开新实验。

## 2. 决策

### 2.1 沙箱 = 执行器边界

沙箱不是提示词。一条回放「已执行」成立，当且仅当：

1. **执行器不在现仓。** guest 的 cwd / checkout 不是宿主 `repo_root`。
2. **现仓对 guest 不可写。** MUST NOT 将现仓以可写 virtio-fs/9p 挂进 guest；注入用
   快照拷贝或只读介质。
3. **出站通道只有回执。** vsock / virtio-serial（或等价）吐出 guest-proof；默认无网络。
   需要模型 API 时 MUST 是合同 egress allowlist，否则 guest 只做 R0/R1（不调模型）。
4. **回执可证伪**（见 §3）。缺项或 `same_checkout=true` → `valid=false`，
   `environment_blocked`，不得宣称回放已执行。
5. **分级不得混称**（见 §2.2）。

「写回当前工作区」仍是宿主危险第二步，默认关闭，不在 guest 合同内。

### 2.2 隔离级别

| 级别 | 是什么 | 可否当「已回放」 |
| :--- | :--- | :--- |
| Lsoft | 提示词 / Control 信封 | 否，只是 instructions |
| Lns | 同机 worktree / bwrap | 否（降级观测）；无 VM 时 R2 只能 `environment_blocked` |
| Lvm | guest VM + guest 内 Agent/CLI | 是，Canvas 主路径 |

Hypervisor 是 adapter，条款 MUST NOT 写死专名（Firecracker / QEMU / CubeSandbox 等）。
实现允许的 Lvm 后端含自建 qemu 镜像与 CubeSandbox（E2B API）；选不到可用后端时
fail closed，**不得**退回宿主 Composer 执行回放体。现仓 MUST NOT 以 host-mount
可写方式进入 guest。

### 2.3 Canvas / 宿主边界

宿主（Canvas / `ndf_replay.py guest-run`）只准：

- 按 recorded `repo_head` 做只读快照（非 `git checkout` 现仓）；
- 启动 guest，传入 episode/commit、只读 replay store 拷贝；
- 等待回执，销毁 guest，展示 JSON。

宿主 MUST NOT：`newComposerChat` 跑 reconstruct / isolate / 原 hop 组装 prompt 作为
回放体。若平台只能打开 Composer，则 Composer 只准跑 `guest-run` 启动器并报告回执，
且 MUST 标为 host launcher instructions，不得把 Lsoft/Lns 标成已回放。

Guest 内才是回放执行器：独立磁盘上的 recorded HEAD + `.ndf/replay` 副本；跑 R0
reconstruct；有磁带再跑 R2。重新调用模型仍属 R3。

### 2.4 R2 adapter

R2 执行 adapter MUST 为 `bwrap` **或** `vm`。无可用 VM 且无合格 bwrap 时 MUST
`environment_blocked`，不得记 passed。Canvas 主路径以 `vm`（Lvm）为准；`bwrap` 仅
作降级观测，不得冒充 Canvas「已回放」。

## 3. Guest-proof schema

```text
schema: ndf-replay-guest-proof/v1
valid: bool
episode_id | commit_sha
isolation:
  adapter: vm
  guest_id | image_sha
  recorded_repo_head
  guest_toplevel | host_toplevel
  same_checkout: false   # MUST
  host_tracked_unchanged: true   # MUST
  host_head_unchanged: true
  bwrap_used: false
execute: { attempted, level, state? }
reconstruct: { level, side_effects: false, ... }
```

校验失败（缺字段、`same_checkout`、宿主 tracked 变化、guest marker 出现在宿主根）
→ `valid=false`。

## 4. 拟落地条款

1. 在 [[META-013]] 增补「回放沙箱与执行器边界」小节（或新增 {#META-015} 并
   `depends-on=META-013`）：写入 §2–§3。
2. 工具：`ndf_replay.py guest-run --commit --episode`（宿主 launcher）。
3. Canvas Replay：沙箱回放按钮只启动 `guest-run`；去掉 hop/prefix 在现仓跑
   reconstruct/isolate 的执行路径。
4. skill / actions：对齐 Lvm 主路径与 proof 验收口径。

## 5. 非目标

- 不把 `isolate` worktree 升级为「真沙箱」。
- 不靠加长提示词冒充隔离。
- 不在本提案写入产品功能专名。
- 不修改 `.openclaw/state.json` 作为回放副作用。
- 不把具体 hypervisor 专名（含 CubeSandbox）写入 META must 正文。

## 5b. 实现注记：CubeSandbox 作为允许的 Lvm 后端

调研结论（见本地 plan / CubeSandbox fit study）：
[TencentCloud/CubeSandbox](https://github.com/TencentCloud/CubeSandbox)（Apache-2.0，
KVM MicroVM + E2B SDK）**可以作为**回放的 Lvm 硬件后端，**不能**替代本提案的
执行器边界 / guest-proof 合同。

约束（落地工具时 MUST）：

1. 条款与 proof 仍使用 `adapter=vm`（Lvm）；实现 CLI 可用 `--adapter cube`，
   proof 记 `hypervisor_backend=cube` / `guest_id=<sandbox_id>` /
   `image_sha=<template_id|hash>`。
2. **禁止** `metadata.host-mount`（或等价）把宿主 `repo_root` 可写挂进 guest；
   只允许 git archive / Volume 拷贝 / files API 注入。
3. 默认 air-gap（无网络）；未部署 Cube / API 不可达 → `environment_blocked`，
   MUST NOT 退回 Composer / `isolate` / `fake-vm` 并宣称已回放。
4. Cube 不是 Replay SoT；Episode 仍在 `.ndf/replay`。
5. Canvas 只启动 `guest-run`，不直接调 E2B / OpenClaw cube-sandbox skill 跑回放体。

## 6. 验收

1. 无 KVM/无合格 hypervisor / 无 Cube API → `guest-run` 返回 `environment_blocked`，`valid=false`。
2. 合格 guest 回执：`same_checkout=false` 且宿主 tracked 相对启动前不变。
3. Canvas 不得在无 guest-proof `valid=true` 时显示「已回放」。
4. `host-mount` 现仓路径 MUST 被拒绝（负例）。
5. `python3 spec/meta/tools/ndf_graphcheck.py --meta` hard_errors=0（条款落地后）。

---

**落地摘要（2026-08-17）**：新增 [[META-015]]；窄改 [[META-013]]（R2 adapter=`bwrap|vm`、
Canvas→guest-run、已回放须 guest-proof）。`ndf_graphcheck.py --meta` hard_errors=0。
工具/Canvas 实现已先于条款（guest-run / cube adapter / 禁 host-mount）。

提案已落地。变更摘要：`META-015` 回放沙箱与执行器边界；`META-013` 对齐 Lvm 主路径。

### Review receipt（[[META-014]]）

```text
kind: proposal.reviewed
proposal_id: meta-replay-sandbox
flow_id: meta-replay-sandbox
hop: review
phrase: 已审核
actor: Human
approved_at: 2026-08-17T17:02:28Z
source_ref: chat
status: reviewed
validation_status: n/a
perf_status: n/a
```

Process track 已结束；无 Trunk 编译/性能验证。
