# Process 提案：恢复文字优先的 POC 主路径

> track: process
> Status: Implemented on 2026-08-24
> 日期: 2026-08-24
> 修改: BEH-025, META-010, META-011, META-012, META-013（热路径收敛）；新增 [[ADR-META-003]]；
> 工具 `poc-dispatch`；Commander 默认只读
> depends-on: CHR-008, BEH-018, BEH-019, BEH-025, META-007, META-008, META-010, META-011, META-012
> 范围: Idea→POC→继续/关闭日常热路径；不改 promote 证据门槛

## 1. 问题

可视化 Commander 与 Episode/Replay/action 闭环把**控制面**抬成了 POC **业务热路径**：

1. 日常探索从「提案 → 装订文档 → 人口令 → 委派 Claude Code → 继续/关闭」膨胀成
   芯片、租约、snapshot freshness、gate/binder 流水线、Repair、Replay 多跳。
2. 委派准备常耗费数十分钟修文档一致性与面板红灯，而真正探索不足。
3. 任务实质完成（代码/测量已落地）仍会因旧 Episode / attempt / projection /
   审计字段不匹配被判失败（假失败），进一步放大成本。

NDF 本意是让人理解 AI 在做什么并聚焦产品探索；当前变成「修面板与回执」。

## 2. 决策

### P1 — 文字指挥是 POC 主路径

日常 POC MUST 以聊天/口令指挥，不依赖 Commander 按钮写 SoT。目标环：

```text
Idea → OpenClaw 写产品提案 → Human「已确认」/「已审核」
→ OpenClaw 一次写齐 TOPIC/DESIGN/PERF_BASELINE/DELTA/INTERFACE（及测试计划）
→ Human「派发」绑定当前契约 bundle SHA
→ Claude Code 实现/测量 → Human 选「继续」或 close 模式
→ 继续：OpenClaw 修订装订器 → 再「派发」
```

三闸串行口令（TOPIC已审核 → DESIGN已审核 → 可以开始实现）改为 **legacy/可选**。
新托管主题 MAY 用单次回执 `bundle_dispatch`（phrase=`派发`）代替闸 3，绑定
装订器契约 bundle SHA。旧主题仍可用三闸；工具 MUST 同时认两者。

### P2 — 硬安全门 vs 软审计

POC 写派发硬阻塞仅：

1. `repo_root` + topic 身份绑定；
2. Human「派发」回执绑定**当前**契约 bundle SHA（未实质 amend）；
3. `allowed_write_root=poc/<topic>/` + isolation 通过；
4. 同 topic 无并发写 run；隔离 worktree / base_sha 可证；
5. context manifest/plan 在发送时有效；
6. 磁盘 `ndf-agent-completion/v1` 的 topic/task/run 身份匹配；
7. ACP context 不超预算。

下列 MUST NOT 单独挡住日常 `poc-dispatch`：meta graph、全量 bindcheck、
projection freshness、button-action commit、Replay 完整度、缺非必要 completion
字段、默认 runtime probe、Commander snapshot 刷新。产品 graph / bindcheck /
完整证据在提案收口、实质 amend、close/promote 时集中执行。

### P3 — 单入口委派内核

新增 CLI：

```text
python3 spec/meta/tools/ndf_workflow_status.py poc-dispatch \
  --topic <topic> --intent implement|measure [--send] [--json]
```

一次完成：读已批准 bundle → 轻量 context verify → 创建或复用隔离租约 → pack →
（`--send` 时）dispatch-send + 最小 completion 校验。`prepare-acp-lease` /
`action-begin|commit|finish` 两步派发保留为 legacy/debug。

### P4 — Commander 只读观察

Commander MUST 默认只投影业务状态（假设、文档版本、最近结果、下一决策）。
POC 写动作（delegate-poc、lease、gate/binder pipeline、repair、Replay 主入口）
`commanderSurface=false` 或仅出现在 Advanced 诊断。Overview MUST NOT 用 Control
错误 KPI 冒充业务红灯。无 Commander 亦 MUST 能完成完整 POC 环。

### P5 — Episode/Replay 降级

META-013/015 能力保留为审计/争议工具。日常 `poc-dispatch` MUST NOT 要求完整
Episode DAG 或 Guest VM 证明才标任务成功；实质成功以磁盘 completion + 写根/
isolation 为准。

## 3. 落地

| 面 | 路径 |
|----|------|
| 条款 | `spec/meta/process.md` BEH-025 / META-010…013 薄修订 |
| ADR | `spec/meta/decisions/adr-meta-text-first-poc.md` [[ADR-META-003]] |
| 指挥手册 | `AGENTS.md` 日常 POC 改回文字流程 |
| 内核 | `ndf_workflow_status.py poc-dispatch` |
| UI | `action-registry.json` + cockpit readiness / 默认面 |
| 测试 | `test_ndf_poc_dispatch.py` |

## 4. 非目标

- 不放松 promote / partial 的证据、语义核、金标义务。
- 不删除 legacy gate/pack/dispatch 入口（本轮仅旁路）。
- 不把 Harness 包反推为本地 SoT。

## 5. 验收

1. 已批准 POC bundle 后，一次「派发」+ `poc-dispatch --send` 即可启动 Claude Code。
2. 无人工 lease / snapshot / repair 步骤。
3. Claude Code 实质完成后，不得仅因旧 Episode/projection 判失败。
4. Commander 关闭时仍可完成 Idea→继续/关闭环。
