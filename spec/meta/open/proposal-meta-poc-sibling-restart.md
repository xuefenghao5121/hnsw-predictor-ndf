# Proposal: POC 关闭后重启一律平级新 topic {#PROP-META-POC-SIBLING-RESTART}

> track: process  
> Status: Implemented on 2026-08-08  
> 日期: 2026-08-08  
> 关联: [[BEH-020]], [[BEH-025]], [[BEH-018]]  
> 场景: 流程 / 装订  
> 原则: 禁止同 topic_id 重开；Harness / state.json 不动

## 1. 动机

依赖工作就绪后，需再试曾 `rejected` 或全量 `promoted` 的方向。现行 [[BEH-025]]
有分叉平级 topic，但未禁止把关闭主题 status 改回 `exploring`。

## 2. 决策

1. [[BEH-025]]：关闭主题（`rejected`/`promoted`）MUST NOT 同 id 重开；重试 MUST 新建
   平级 `poc/<new-topic>/`，`depends_on_topics` 含旧题（及使能依赖）；新 R0；不得从
   archive 迁回冒充新开题。仍 `exploring`/`blocked`（含 partial）= 同题继续，非本条。
2. [[BEH-020]]：再探索见 [[BEH-025]]；MUST NOT 原地复活 `rejected`。
3. `AGENTS.md`、`poc/README.md` 薄同步。

## 3. 冻结

`packages/ndf-harness/**`、`.openclaw/state.json` 零改动。

## 4. 验收

条款 + AGENTS + poc README 含上述 MUST；`graphcheck --meta` hard_errors=0。
