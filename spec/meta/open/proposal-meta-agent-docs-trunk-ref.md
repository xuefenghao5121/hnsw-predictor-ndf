# Proposal: 工作流文档同步 META-005 / trunk-ref {#PROP-META-AGENT-DOCS-TRUNK-REF}

> track: process  
> Status: Implemented on 2026-08-06  
> 日期: 2026-08-06  
> 关联: [[META-001]], [[META-005]], [[BEH-019]], [[META-004]], [[ADR-META-001]]  
> 场景: 规范卫生 / Agent 说明书同步  
> 原则: 产品无关；Harness 有意冻结

## 1. 动机

[[META-005]] / `trunk-ref` 已写入 `spec/meta/language.md` 与 [[BEH-019]]，但
`AGENTS.md`、`spec/meta/README.md`、Cursor / Claude 说明书、`MEMORY.md` 仍停在
META-001…004，promote 清单未要求 SLA↔API 图边与 git SHA 绑定。

## 2. 决策

1. 更新 [`AGENTS.md`](../../../AGENTS.md)：启动读序与权威条款含 META-005；promote
   清单补 SLA `depends-on` API + `trunk-ref=`；禁止跳过即宣称性能 SLA 收口。
2. 更新 [`spec/meta/README.md`](../README.md)：语言 SoT 至 META-005；Harness 旁注滞后。
3. 重写 [`.cursor/rules/ndf-workflow.md`](../../../.cursor/rules/ndf-workflow.md) 为薄指针。
4. 补 [`.claude/CLAUDE.md`](../../../.claude/CLAUDE.md)：L1 env/SLA/`trunk-ref` 由 OpenClaw 维护。
5. 刷 [`MEMORY.md`](../../../MEMORY.md) 速览指针（非 SoT）。

## 3. 冻结

**`packages/ndf-harness/**` 零改动**。滞后为有意冻结；待近期 meta 变更积齐后
**统一重提炼**。禁止用 Harness 反推本地 `spec/meta/`（[[ADR-META-001]] / 本地 SoT 纪律）。

## 4. 非目标

- 不改 `spec/00–50` / META-005 正文
- 不加 graphcheck hard rule
- 不蒸馏 Harness

## 5. 验收

- `rg 'META-005|trunk-ref'` 命中 AGENTS、meta README、ndf-workflow、CLAUDE、MEMORY
- `git status packages/ndf-harness` 无本轮变更
- `ndf_graphcheck.py --meta` hard_errors=0
