# Process 提案：Genesis 初始化工作流 remaining bugs

> track: process
> status: Implemented
> Status: Implemented on 2026-08-24
> reviewed: 已审核
> plane: process
> control-flow: managed
> proposal-id: meta-workflow-init-bugs
> flow-id: meta-workflow-init-bugs
> 日期: 2026-08-24
> 修改: META-009 / META-011 薄补；genesis-status / dispatch closeout / hop 推断 / skill
> depends-on: META-009, META-010, META-011, META-014
> 范围: NDF 指挥面初始化轨与 dispatch 成功合同；不改产品 Trunk、不盖 Genesis 闸
> land-targets: spec/meta/process.md, spec/meta/tools/ndf_dispatch_send.py, spec/meta/tools/ndf_workflow_status.py, spec/meta/tools/test_ndf_dispatch_disk_first.py, spec/meta/tools/test_ndf_genesis_status_gates.py, spec/meta/tools/test_ndf_worker_pack_intent.py, AGENTS.md, .cursor/skills/ndf-workflow/genesis.md, .cursor/skills/ndf-workflow/delegate.md, .cursor/skills/ndf-workflow/SKILL.md

Status: Implemented on 2026-08-24 (human phrase `已确认` at 2026-08-24T18:55:51Z).

人类原话：`把meta工作流的bug都修复好`。

本提案收口本仓 Genesis 初始化中已观测、仍未对齐 SoT 的流程缺陷。
已落地且不在本提案范围：OpenClaw 每 hop `sessions.reset`；slim pack 保留
`request.intent`；Genesis 被标成 `track=poc` 时 fail-closed。

## 1. 观测（工具违反已有条款）

### 1.1 成功合同：代码要求 stdout notify，条款要求磁盘回执

[[META-011]] 已写：validated completion 以 pack 钉死的 `completion_receipt_path`
上磁盘 `ndf-agent-completion/v1` 为准；stdout `ndf-dispatch-notify/v1` 仅运输辅助。

`ndf_dispatch_send._task_outcome_from_transport` 在 notify 缺失时直接
`missing_dispatch_notify` 失败，**不读** pack 钉死路径上的磁盘回执。
后果：worker 已写磁盘 completion + 产物，Command 仍报失败，并误把下一串行闸当
「本 hop 未完成」。

### 1.2 Genesis hop 推断把「禁止写 Architecture」当成 Architecture hop

`infer_genesis_hop` 先搜 `ARCHITECTURE` 再搜 `CHARTER`。CHARTER intent 若写
「MUST NOT write Architecture until CHARTER已审核」，会被标成
`hop=genesis_architecture`。Command 随后一直纠结 Architecture。

### 1.3 `genesis-status` 不读 `GATES.md`，跳过 Foundation 串行口令

`genesis_status()` 用粗成熟度：有 `FOUNDATION.md` + 已有 `src/` →
`trunk_candidate`，G1 标 completed，G1 `next_phrase` 写死 `VERIFICATION已审核`，
`next_step` 变成 `可以建立初始主线`。

这与 [[META-009]] 串行口令
`CHARTER已审核 → ARCHITECTURE已审核 → VERIFICATION已审核 → 可以建立初始主线`
以及 Genesis `GATES.md` 冲突。指挥面跟 CLI 会指到不同下一句。

### 1.4 Foundation「已审核」被当成产品 L0 落地

[[META-009]] 写「确认后的目标进入产品 Charter」，但 Foundation 各 hop 实际只在
`spec/open/project-genesis/` 写 review 草稿，且禁止写入 `spec/00-charter/`。
Command 把 `GATES.md` 的 `CHARTER已审核` 当成 Charter 已落地，推进 Architecture。
人类认知合同是确认 → 落地 → 审核；闸门表前进 ≠ `spec/00-charter/` 有正文。

### 1.5 各 hop 共用同一 completion 路径

topic-less idea pack 落在
`spec/open/.ndf-completion/product_proposal-attempt.json`。
CHARTER / 误写产品提案 / ARCHITECTURE 互相覆盖，身份无法按 hop 对账。

### 1.6 bootstrap context_plan.topic 为空

`control_proposal_idea_pack` 在 `track=bootstrap` 时 pack `topic` 已是
`project-genesis`，但 `context_binding(topic=None)`，worker 看到
`context_plan.topic: null`。notify 身份曾因此 `missing_notify:topic`。

## 2. 决策

薄补 [[META-011]]、[[META-009]]（不新开 `META-*` 号）。

### 2.1 磁盘优先 closeout {#META-011}

1. `dispatch-send` 在 transport_ok 后 MUST 读取 pack 钉死的
   `completion_receipt_path`。有效磁盘 `ndf-agent-completion/v1` 且
   topic/task/hop/episode/attempt 与 pack 匹配 → hop 成功。
2. stdout `ndf-dispatch-notify/v1` MAY 作为运输辅助去定位 receipt；
   notify 缺失 MUST NOT 单独把已有合法磁盘回执判失败。
3. 磁盘回执缺失或身份不匹配 → fail-closed（`missing_disk_receipt` /
   identity mismatch）。不得用 transport ACK 冒充。
4. bootstrap hop 的 receipt 路径 MUST 含 `hop`（及 attempt），MUST NOT
   让不同 Foundation hop 覆盖同一 `product_proposal-attempt.json`。

### 2.2 Genesis hop 身份 {#META-011}

1. intent 头部 `hop: genesis_charter|genesis_architecture|genesis_verification|genesis_trunk`
   MUST 优先于正文子串。
2. 无头部时 MUST 按串行顺序推断（CHARTER → ARCHITECTURE → VERIFICATION → trunk），
   MUST NOT 因正文出现「ARCHITECTURE」或「MUST NOT write Architecture」而跳到 Architecture。
3. 无 `hop` 的 bootstrap pack MUST `genesis_hop_unlabeled` fail-closed。
4. bootstrap `context_plan.topic` MUST 等于 pack `topic`（notify 身份，非 POC `topic_dir`）。

### 2.3 genesis-status 以 GATES 为下一句 SoT {#META-009}

1. `genesis-status` 的 `next_step.phrase` MUST 等于 Genesis `GATES.md` 中
   第一条 `status=pending` 的串行口令（角色已配置…GENESIS已审核）。
2. 不得因「已有 `src/` + FOUNDATION.md」把 G1 标 completed 并跳到
   `可以建立初始主线`。
3. 粗成熟度 `trunk_candidate` MAY 保留为 adopt 观察项，MUST NOT 覆盖
   `GATES.md` 的下一句口令。

### 2.4 审核回执 ≠ L0 落地 {#META-009}

1. Foundation 分段口令（CHARTER/ARCHITECTURE/VERIFICATION 已审核）审核的是
   `spec/open/project-genesis/` 下的 review 草稿。
2. MUST NOT 把这些口令解释为已写入 `spec/00-charter/` / `spec/10-architecture/`
   / `spec/50-verification/` 的稳定 L0/L1。
3. 产品 Charter/Architecture/Verification 树的稳定写入留到 Foundation 草稿齐
   且人类未反对之后的落地（默认 `GENESIS已审核` 前的 land hop，或提案另指定）。
   adopt 仍 MUST NOT 改写 git 历史。
4. Command 下一 hop MUST 是：失败 closeout → 同一 hop「继续」；人类明确
   「Charter 未落地」→ Charter 落地/修订，MUST NOT 送 Architecture。
5. `GATES.md` 文件存在或已盖章 MUST NOT 单独推出下一串行实现 hop
   （[[META-010]] gate drift）。

## 3. 非目标

- 不改产品 `src/` / `include/` / `tests/`
- 不伪造 Genesis `GATES.md` `approved_by`
- 不把本仓 Charter 草稿写入 `spec/00-charter/`（那是产品/bootstrap 落地，另等人审）
- 不回退已落地的 session reset / intent-in-slim / genesis-not-poc fail-closed
- 不同步 `packages/ndf-harness/` 上游包

## 4. 落地清单（确认后）

| 文件 | 改动 |
|------|------|
| `spec/meta/process.md` | META-011 磁盘优先 + hop 路径；META-009 审核≠落地 + genesis-status 读 GATES |
| `ndf_dispatch_send.py` | `_task_outcome_from_transport` 磁盘优先；receipt 路径含 hop |
| `ndf_workflow_status.py` | `infer_genesis_hop` 串行；`genesis_status` 读 GATES；bootstrap context topic |
| tests | 无 notify 有磁盘回执 → success；CHARTER intent 含 Architecture 禁写 → charter hop；genesis-status next_phrase 跟 GATES |
| `AGENTS.md` + skill `genesis.md` / `delegate.md` / `SKILL.md` | 薄指针：失败 closeout 同 hop；已审核≠00-charter 落地 |

## 5. 验收

- `python3 spec/meta/tools/ndf_graphcheck.py --meta` hard_errors=0
- 上表 self-check 测试通过
- 人为构造：transport_ok、无 stdout notify、pack 路径上合法 completion → dispatch 结果 success
- CHARTER intent 含 “MUST NOT write Architecture” → `hop=genesis_charter`
- 有 `src/` + FOUNDATION、但 GATES `architecture_review=pending` → `next_step.phrase=ARCHITECTURE已审核`（若 charter_review 已 approved）

## 6. 本 hop 不派发 OpenClaw

提案由指挥面写入 `spec/meta/open/`。确认后同宿主落地 `land-targets`。
不为此提案再开 Control `dispatch-send`。

## Control receipts

| event | phrase | actor | at | proposal_sha | flow_id | hop | status |
|---|---|---|---|---|---|---|---|
| proposal.confirmed | 已确认 | human | 2026-08-24T18:55:51Z | 91463a7e047326df027c8ce8fe500ddd70ce5c41f4cb46243e418970a8f77e20 | meta-workflow-init-bugs | confirm_land | valid |
| proposal.reviewed | 已审核 | human | 2026-08-24T18:57:06Z | 91463a7e047326df027c8ce8fe500ddd70ce5c41f4cb46243e418970a8f77e20 | meta-workflow-init-bugs | review | valid |

