# Process 提案：Genesis 收成内核绑定 + 一次设计 hop

> track: process
> status: Implemented
> Status: Implemented on 2026-08-24
> reviewed: 已审核
> plane: process
> control-flow: managed
> proposal-id: meta-genesis-kernel-bind
> flow-id: meta-genesis-kernel-bind
> 日期: 2026-08-24
> 修改: META-009 / META-010 薄补；genesis-status / hop / Control 写根 / skill
> depends-on: META-009, META-010, ADR-META-003
> 范围: bootstrap 初始化形状；不改 Trunk 代码
> land-targets: spec/meta/process.md, spec/meta/templates/genesis/FOUNDATION.md.stub, spec/meta/tools/ndf_workflow_status.py, spec/meta/tools/test_ndf_genesis_status_gates.py, spec/meta/tools/test_ndf_genesis_kernel_bind.py, AGENTS.md, ndf.workflow.yaml, .cursor/skills/ndf-workflow/genesis.md, .cursor/skills/ndf-workflow/delegate.md, .cursor/skills/ndf-workflow/SKILL.md, .cursor/skills/ndf-workflow/roles/control.md

Status: Implemented on 2026-08-24（执行 plan「擦掉重来」时一并落地）。

人类原话：初始化只是绑定 NDF 内核；擦掉半成品 Genesis，优化流程后重新初始化；
委派设计 Agent 在 `spec/` 下写入项目全部产品 NDF。

## 1. 问题

[[META-009]] 把 bootstrap 做成 CHARTER→ARCHITECTURE→VERIFICATION 三闸连派 OpenClaw，
比日常 POC 文字优先更重。Foundation 草稿在 `spec/open/project-genesis/`，与最终
`spec/00–50` 产品树重复。adopt 仓仍要求 genesis-pack，但 Trunk 已存在。

## 2. 决策

薄补 [[META-009]]、[[META-010]]（不新开号）。

### 2.1 新 bootstrap 形状 {#META-009}

1. **G0 内核绑定**（Command）：写 `spec/open/project-genesis/FOUNDATION.md` +
   `GATES.md` 骨架；记录 `bootstrap_mode`、`observed_trunk_sha`、roles SHA；不派 OpenClaw。
2. **G1 设计 hop**（Control，一次）：人「派发」→ `hop=genesis_design` → 对照 Trunk
   盘点，写入 `spec/00-charter/` … `spec/50-verification/`（默认 `status=draft`）；
   MUST NOT 写 `spec/meta/` stable 正文。
3. **G2 初始主线**（仅 `greenfield`）：人「可以建立初始主线」→ 一次 `genesis-pack`。
4. **G3 冻结**：人「GENESIS已审核」→ operational。`adopt` 跳过 G2。

串行人口令（新主题）：

```text
角色已配置 →（Command 绑内核）→ 派发 → GENESIS已审核
```

`greenfield` 在「派发」与 `GENESIS已审核` 之间插入 `可以建立初始主线`。

### 2.2 作废未冻结 bootstrap {#META-010}

收到 `GENESIS已审核` 之前，bootstrap 产物 MAY 整树作废（删 `spec/open/project-genesis/`、
重置 GATES），不必 append-only 续写旧 Foundation 审稿回执。

### 2.3 legacy 禁派

Command MUST NOT 对 `genesis_charter` / `genesis_architecture` /
`genesis_verification` / `genesis_foundation` 造 pack；fail-closed
`genesis_per_draft_dispatch`。

## 3. 验收

- `python3 spec/meta/tools/test_ndf_genesis_status_gates.py`
- `python3 spec/meta/tools/test_ndf_genesis_kernel_bind.py`
- `python3 spec/meta/tools/ndf_graphcheck.py --meta` hard_errors=0
