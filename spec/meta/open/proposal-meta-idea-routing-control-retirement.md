# Process 提案：Idea 分流与控制面完整退役

> track: process
> Status: Implemented on 2026-08-24
> 日期: 2026-08-24
> 修改: META-011, META-012, META-013, META-014, META-015；新增 [[ADR-META-004]]；
> 工具 Idea 平面分流、`poc-dispatch` 内核；退役 Commander / Episode / Replay 热路径
> depends-on: CHR-008, BEH-025, META-008, META-009, META-010, ADR-META-003
> 范围: Idea 路由、文字委派安全内核、可视化/回放退役；不改 promote 证据门槛

## 1. 问题

1. 人工 Idea 曾混用同一 `control_proposal` 写根（`spec/open/` + `spec/meta/open/`），
   产品与 NDF 流程提案容易一刀切落错平面。
2. Commander、ActionSpec、snapshot freshness、Episode/Replay/Guest 占用人类注意力，
   与「少则得」目标冲突；[[ADR-META-003]] 已降级热路径，但仍保留面板/回放义务。
3. Meta Skills 入口过多（canvas / replay / harness / 薄 ndf-workflow），项目初始化
   仅覆盖 Genesis G0。

## 2. 决策

### P1 — Idea 平面分流

| Idea 类型 | 落点 |
|-----------|------|
| 产品能力、运行中项目、bug、性能、POC、Genesis | `spec/open/` |
| NDF 语言、工作流、Agent 编排、治理工具、规范卫生 | `spec/meta/open/` |
| 同时影响两面 | 拆成两个互相引用的提案；无法判断时先问人 |

任务拆分：`product_proposal`（仅 `spec/open/`）与 `process_proposal` /
`ndf_improvement_proposal`（仅 `spec/meta/open/`）。路径、plane、track 不一致
MUST fail closed。共享 `control_proposal` 保留为兼容别名，默认映射到产品平面。

### P2 — 控制面完整退役

退役日常义务：Commander UI、`action-registry`、snapshot freshness、serve/SSE、
Action begin/commit/finish、Episode DAG、Replay、Guest VM、button-action 账本。
历史 `.ndf/replay/` 保持原地只读，不再生成，不作为成功判定输入。

### P3 — 最小文字派发安全内核

保留硬门：`repo_root`/topic 身份、人审 bundle SHA、`allowed_write_root` + isolation、
同 topic 单写 run、context verify、ACP 预算、磁盘 `ndf-agent-completion/v1` 身份、
写边界复检。成功仅由执行安全与磁盘 completion 决定。

### P4 — 唯一人类 Skill 入口

收敛为 `.cursor/skills/ndf-workflow/`：intake / genesis(G0–G3) / proposal / poc /
close / health / delegate。人类五类输入：初始化项目、提交 Idea、派发、继续、关闭。

## 3. 条款修订摘要

- META-011：删除 Commander/投影/action/serve 义务；只保留文字委派与磁盘 completion。
- META-012：删除 Canvas/Episode 绑定义务；保留 Manifest、写根、上下文与预算。
- META-013、META-015：`status=deprecated`；历史说明保留，不再要求运行。
- META-014：简化为路径分流 + `已确认`/`已审核`；删除 child Episode / Replay 对账。
- 新增 ADR-META-004（减法决策）。

## 4. 兼容

- `control_proposal` → `product_proposal` 别名。
- 旧 CLI `poc-dispatch` 子命令转发到抽取模块。
- 旧 Commander/Replay 测试删除或改为内核负测。
