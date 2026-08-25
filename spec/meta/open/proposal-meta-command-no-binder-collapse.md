# Process 提案：Command 不得代写装订器 / Control 开题可派发

> track: process
> status: Implemented
> plane: process
> control-flow: managed
> proposal-id: meta-command-no-binder-collapse
> flow-id: meta-command-no-binder-collapse
> 日期: 2026-08-25
> depends-on: META-010, META-011, META-014, BEH-025, ADR-META-003, ADR-META-004
> 范围: NDF META 指挥面写界与 Control `binder_pipeline` 开题派发；不改产品 Trunk / DiskHNSW
> land-targets: spec/meta/process.md, spec/meta/tools/ndf_workflow_status.py, spec/meta/tools/ndf_dispatch_send.py, spec/meta/tools/ndf_perf_baseline.py, AGENTS.md, .cursor/skills/ndf-workflow/SKILL.md, .cursor/skills/ndf-workflow/delegate.md, .cursor/skills/ndf-workflow/poc.md, .cursor/skills/ndf-workflow/proposal.md
> scope=ndf-process

Status: Implemented on 2026-08-25 (human phrase `已确认` at 2026-08-25T08:08:46Z).
Reviewed: 2026-08-25T08:32:00Z (human phrase `已审核`).

人类原话：纠偏——不管是初始化流程还是日常 POC 流程，指挥面都不应该直接参与实现；在 NDF META 工作流中先把这个 bug 修补。

## 1. 观测（bug）

### 1.1 条款缝隙：禁止「实现/测量」未覆盖装订器 SoT

[[META-011]] 写 Command MUST NOT 代写 worker「实现/测量」，但日常 POC 在产品提案
「已审核」后，装订器正文属 **Control** 写界（`poc/<topic>/ndf/`）。条款未显式禁止
Command 手写 TOPIC/DESIGN/PERF_BASELINE/DELTA/INTERFACE，指挥面易在 OpenClaw 未就绪时
**塌缩代写装订器**，破坏三层能力与磁盘 completion 合同。

同问题亦见于：Genesis / 日常 POC 凡属 Control 或 Implementation 写界的产物，指挥面
不得用「赶进度」绕过 pack →「派发」→ worker。

### 1.2 工具鸡生蛋：`binder_pipeline` 要求已有 `TOPIC.md`

`control-pack --task binder_pipeline --topic T` 在 `poc/T/ndf/TOPIC.md` 缺失时直接
`unknown topic`。产品提案已审核后，**无法**在不先造 topic 树的情况下派 Control 开题，
逼指挥面先写占位/全文装订器 → 与 1.1 叠加。

### 1.3 `runtime_unavailable` 硬挡，吞掉已配置 fallback

Control `adapter=openclaw` 且 gateway 不可达时，pack `blockers: [runtime_unavailable]`
且 `safe_to_dispatch=false`。即使 `ndf.workflow.yaml` 已配 `fallback: in-host`，
指挥面在「派发」前被拦住；`dispatch-send` 内对 `openclaw_cli_missing` 的 fallback
路径也走不到。结果再次诱导 Command 代写。

### 1.4 附带工具缺陷：`ndf_perf_baseline` 空 `evidence_status` 崩溃

`inspect_topic` 对空 `evidence_status` 做 `.split()[0]` → `IndexError`，污染 topic-health
（`perf_baseline_failed`），与装订器是否合法无关。

## 2. 决策（薄补 [[META-011]]；工具对齐；不新开 META 号）

### 2.1 Command 写界收紧 {#META-011}

1. Command MUST NOT 将下列路径作为 SoT 正文作者（Genesis 与日常 POC 相同）：
   - `poc/<topic>/ndf/` 装订器 facet 正文（TOPIC/DESIGN/PERF_BASELINE/DELTA/INTERFACE/COMMITS）
   - Implementation 写界：`poc/<topic>/` 代码与测量、Trunk `src/`/`include/`/`tests/`（按 track）
   - 产品契约落地正文：未经 Control hop + 磁盘 completion，MUST NOT 代写 `spec/00–50` /
     产品 `spec/open/proposal-*.md` 的契约切片（process 提案仍可按 [[META-014]] 由指挥面起草）
2. Command 仅可：造 pack、记人类口令回执（经 CLI / 明确回执工具）、读状态、报告 blockers。
3. MUST NOT 以「OpenClaw 宕机 / 赶文字优先」为由手写装订器；须走 fallback adapter 或报告
   `runtime_unavailable` / `role_adapter_unsupported` 等人处理。

### 2.2 开题：`binder_pipeline` 可自提案创建 topic {#META-011}

1. 产品提案 `status=reviewed`（或等价「已审核」回执有效）后，
   `control-pack --task binder_pipeline --topic <t>` MUST 允许 `<t>` 尚无
   `poc/<t>/ndf/TOPIC.md`。
2. 此时 pack MUST 把 `allowed_write_roots` 扩到 `poc/<t>/ndf/`（整目录创建权限），
   intent/context MUST 钉死已审提案路径；Control 一次写齐装订器。
3. Command MUST NOT 为满足「topic 存在」而预写 facet 正文；至多 `tmp/` 意图文件。

### 2.3 fallback 优先于硬挡 {#META-011}

1. 解析 Control 角色时：首选 adapter 运行时不可用，且 `fallback` ∈
   `{in-host, dual-session, custom}` 且可解析 → pack MUST
   `safe_to_dispatch=true`（其它硬门仍满足时），`provider`/`delegate_to` 记 fallback，
   MUST NOT 仅因主 adapter `runtime_unavailable` 拒绝「派发」。
2. `dispatch-send` MUST 对 gateway 不可达（不仅 CLI missing）尝试同一 fallback 合同。
3. 无合法 fallback → 保持 fail-closed；Command MUST NOT 代写。

### 2.4 `ndf_perf_baseline` 空字段 {#META-011}（工具卫生）

空或缺失 `evidence_status` / `status` MUST 视为「非 unverified」，MUST NOT 抛
`IndexError`；以 finding 或 pending 表达。

## 3. 落地清单（「已确认」后）

| 面 | 动作 |
|----|------|
| `spec/meta/process.md` | 薄补 META-011 §三层能力 / 文字优先（2.1–2.3） |
| `ndf_workflow_status.py` | binder_pipeline 无 TOPIC 可开题；runtime+fallback 派发判定 |
| `ndf_dispatch_send.py` | gateway 不可达 → fallback |
| `ndf_perf_baseline.py` | 空 split 防护 + 最小自检 |
| `AGENTS.md` + ndf-workflow skill | 薄指针：审核后只造 Control pack，禁代写装订器 |

## 4. 非目标

- 不改 DiskHNSW 产品假设 / hierarchical-vamana 提案正文（产品提案已审仍有效）
- 不在本提案内重跑 POC Implementation
- 不强制回填历史已由 Command 代写的装订器（当前 topic 已降级为占位，等本补丁后 Control 重写）

## 5. 验收

1. 无 `TOPIC.md` 时 `control-pack --task binder_pipeline --topic hierarchical-vamana` 不再
   `unknown topic`（提案已审前提下）。
2. OpenClaw gateway 关闭但 `fallback: in-host` 时，pack 不以单独 `runtime_unavailable`
   置 `safe_to_dispatch=false`。
3. skill/AGENTS 含显式「Command MUST NOT 写装订器正文」。
4. `ndf_perf_baseline.py check` 对空 `evidence_status` 不崩溃。

## Control receipts

| event | phrase | actor | at | proposal_sha | flow_id | hop | status |
|-------|--------|-------|----|--------------|---------|-----|--------|
| proposal.confirmed | 已确认 | human | 2026-08-25T08:08:46Z | 0105194c7d4b12025372acc4888578f5498a1f58e52aea87d1512a3f251482fe | meta-command-no-binder-collapse | confirm_land | approved |
| proposal.reviewed | 已审核 | human | 2026-08-25T08:32:57Z | 0105194c7d4b12025372acc4888578f5498a1f58e52aea87d1512a3f251482fe | meta-command-no-binder-collapse | review | approved |
