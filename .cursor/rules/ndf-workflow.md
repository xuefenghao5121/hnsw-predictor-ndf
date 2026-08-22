---
description: NDF规范开发流程 - AI编码时必须遵循的工作流
globs: src/**,tests/**
alwaysApply: true
---

# NDF 规范开发流程

## 权威（先读）

1. 仓库根 [`AGENTS.md`](../../AGENTS.md)（OpenClaw 指挥；按 track 分流）
2. [`spec/meta/`](../../spec/meta/)：[`README.md`](../../spec/meta/README.md) +
   [`language.md`](../../spec/meta/language.md)（[[META-001]]…[[META-005]]）+
   [`process.md`](../../spec/meta/process.md)（Genesis / 双轨 / 装订 / promote / Canvas）
3. 本地 SoT 纪律： [`.cursor/rules/ndf-local-sot.mdc`](ndf-local-sot.mdc) —
   **MUST NOT** 用 `packages/ndf-harness/` 指导或纠正本地 `spec/meta/`（Harness 冻结待统一重提炼）

冲突时以 `AGENTS.md` + `spec/meta/` 为准。

## 1. 编码前检查清单

编写任何新代码之前 MUST：

- [ ] 项目 maturity 已为 `operational|operational_legacy`；否则先走 [[META-009]] bootstrap
- [ ] 目标行为在 `spec/20-behavior/` 有对应 L1（`{#BEH-*}` 等）
- [ ] 接口在 `spec/30-interfaces/`（如 `env.md` / `cli.md` / `cxx-api.md`）
- [ ] 相关约束/SLA 在 `spec/40-constraints/`（如 `sla.md`）
- [ ] track 已判定（`poc` → 只动 `poc/<topic>/`；promote/bug → 须有提案且经确认）

若缺失：**停止编码**，提示走 OpenClaw 提案（产品 → `spec/open/`；流程 → `spec/meta/open/`）。

Canvas/自动委派还 MUST 校验 [[META-010]] `GATES.md` 内容 SHA 与 [[META-011]]
Claude Code 管道握手；NDF Control 文档流委派 OpenClaw（`control-pack` + `chat_send`）；
文件存在不等于已审核。

## 2. 性能 SLA / 环境变量（[[META-005]]）

写入或验收 Trunk **stable** 性能 SLA 时：

- SLA MUST `depends-on` 声明旋钮的 **API-***（不得只靠正文 env 串）
- 相关 API / SLA MUST 带 **`trunk-ref=`**（完整 git SHA 优先）
- 默认值对齐该 SHA 的 `src/`；测量配置另列
- L1 API / SLA / `trunk-ref` 元数据由 OpenClaw 维护；实现侧只跟已落地条款

细节见 [`AGENTS.md`](../../AGENTS.md) §6.2b 与 [[META-005]]。

## 3. 编码中

- 架构：`spec/10-architecture/modules.md`
- 接口实现对齐 `30-interfaces/`；字段级可在 promote/bug track 细化
- 不违反 `40-constraints/sla.md` 中 stable SLA
- 测试对齐 `50-verification/`

## 4. 编码后自查

- [ ] 关键实现可追溯到条款 ID
- [ ] 未误改 `spec/meta/`、L0/L1、charter、architecture、decisions
- [ ] poc track 未改 Trunk `src/` 生产默认路径

## 5. 规范与代码冲突

1. 指出冲突
2. 优先修代码以匹配规范
3. 若须改规范：产品 → `spec/open/feedback-*.md`；流程 → `spec/meta/open/feedback-*.md`；等确认

## 6. 紧急修复

允许先修代码，然后 MUST：标注临时 workaround + 条款 ID，并开 feedback / 交 OpenClaw 补提案。
