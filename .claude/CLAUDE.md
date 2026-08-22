# CLAUDE.md - Claude Code 行为约束

## 绝对禁区
1. 严禁修改 `spec/00-charter/` 和 `spec/10-architecture/`
2. 严禁修改 `spec/meta/`（NDF process profile；仅 OpenClaw / Cursor 维护）
3. 严禁修改 `spec/20-behavior/` 中 `level=L0` 或 `level=L1` 的条款
4. 严禁修改 `spec/decisions/` 与 `spec/meta/decisions/`
5. 若发现 L0/L1 与代码现实冲突：
   - **产品契约** → `spec/open/feedback-*.md`
   - **流程/双轨/装订** → `spec/meta/open/feedback-*.md`（或交 OpenClaw 开 process 提案）
6. **严禁**把实验补丁写入 `spec/models/` 冒充 L3 金标

## 按 track 的写入范围（权威见仓库根 `AGENTS.md`）

| track | 可写 | 禁止 |
|-------|------|------|
| **bootstrap** | 独立 worktree/branch 中的初始 `src/`、`include/`、`tests/`、构建配置、L2/L3 | L0/L1、charter、architecture、decisions、`spec/meta/`；未获「可以建立初始主线」前开码 |
| **poc** | `poc/<topic>/` only（含 NOTES、独立源码/bench、ndf 装订器证据） | Trunk `src/`、`include/`、`tests/`；stable must SLA；`spec/meta/`。要改的头/源 MUST 先拷进 `poc/<topic>/`（[[BEH-018]]） |
| **promote / bug / refactor / rollback** | `src/`、`include/`、`tests/`、`50-verification/`；L2/L3；字段级接口 | L0/L1、charter、architecture、decisions、**meta** |
| **process** | **不得**自行改 meta/产品条款；若委派仅改 `poc/` 文档则听从说明 | 擅自改 `src/` 或 `spec/meta/` |

不确定时：**默认按 poc**，只动 `poc/<topic>/`。委派前后 SHOULD 跑：
`python3 spec/meta/tools/ndf_poc_isolation.py check --topic <topic>`。

## 性能 SLA / env / `trunk-ref`（[[META-005]]）

- `trunk-ref`、stable 性能 SLA 的 API `depends-on`、以及 `30-interfaces/env.md` 的
  **L1 API** 条款由 **OpenClaw** 维护（见仓库根 `AGENTS.md` §6.2b）。
- Claude 在 promote/bug 可写字段级 env 用法于代码/测试注释，但 **MUST NOT** 改
  L1 API/SLA 元数据，也 **MUST NOT** 伪称已更新 `trunk-ref`。
- **MUST NOT** 以 `packages/ndf-harness/` 为准改本地规范（包冻结，待统一重提炼）。

## POC 装订器读序（[[BEH-025]] / [[META-007]]）

- 实现前 MUST 读 `TOPIC.md` → `DESIGN.md` → `PERF_BASELINE.md`（金标绑定）→ `DELTA.md` →
  `INTERFACE.md` → `proposals/`
- **分段门禁**：未收到用户「可以开始实现」前 MUST NOT 编写主题代码（只读文档/证据除外）。
  开题串行口令：`TOPIC已审核` → `DESIGN已审核` →（写绑定+DELTA）→ `可以开始实现`
  （与产品提案「已审核」分开）
- 自动/Canvas 委派还 MUST 读取 `GATES.md`：`implementation_approval` 回执须有效且
  `approved_content_sha` 与当前绑定文件束一致；文件存在不等于已审核（[[META-010]]）。
- 管道启动握手 MUST 返回 `run_id/session_id`、`base_sha`、独立 worktree/branch 与
  `allowed_write_root`；缺任一项停止写入并报告 `unsafe`（[[META-011]]）。
- 比 Δ% / 压测前 MUST 读 `TOPIC.md` → `perf_baseline` → `PERF_BASELINE.md` + `DELTA.md`
- 数字与配置以该卡（及卡内唯一 `vs:` / `config_id` / `measure_script`）为准；MUST NOT 从
  `sla.md` 抄观测表当 R0
- 配置-only 变更：写清 `cfg-*` 或卡内全量 env，并更新主题卡与 DELTA；MUST NOT 刷 stable SLA 数字
- 工具：`python3 spec/meta/tools/ndf_perf_baseline.py show --topic <id>`
  （装订门禁；数字 SoT 在 `spec/50-verification/`）
- 模板：`spec/meta/templates/poc/{DESIGN,DELTA,INTERFACE}.md.stub`
- 门禁模板：`spec/meta/templates/poc/GATES.md.stub`

## Project Genesis（[[META-009]]）

- `bootstrap_mode=greenfield|adopt`；旧代码接管 MUST NOT 改写历史。
- 门禁：`IDEA已审核` → `CHARTER已审核` → `ARCHITECTURE已审核` →
  `VERIFICATION已审核` → `可以建立初始主线` → `GENESIS已审核`。
- 仅在「可以建立初始主线」有效回执后建立最小可构建垂直切片。
- 无证据的性能值保持 draft/TBD/not-established；不得造初始金标。

## 权限范围（在 track 允许的前提下）
- Trunk 实现：`src/`, `tests/`, `50-verification/`（仅 promote/bug/refactor/rollback）
- 细化权：`20-behavior/`（L2/L3）、`30-interfaces/`（字段级）、`40-constraints/`（数值，非 L0/L1 叙事）
- 提案权：产品 L0/L1 冲突 → `spec/open/`；流程冲突 → 交给 OpenClaw（`spec/meta/open/`）
