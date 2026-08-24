# Proposal: POC 关闭时同步 NOTES.md 状态 {#PROP-META-POC-NOTES-STATUS}

> track: process  
> Status: Implemented on 2026-08-06  
> 日期: 2026-08-06  
> 关联: [[BEH-019]], [[BEH-020]], [[BEH-025]], [[DEF-022]]  
> 场景: 规范卫生 / 装订  
> 原则: NOTES 仅为导航镜像，非 must SoT；Harness 冻结

## 1. 动机

主题关闭后 `TOPIC.md` status 已更新，但 `poc/<topic>/NOTES.md` 常无状态行或仍写
探索中文案，扫 NOTES 易误判主题仍活跃。

## 2. 决策

1. [[BEH-025]]：关闭时若存在 NOTES.md，头字段 MUST 镜像 TOPIC 的
   `promoted`/`rejected`（及日期/关闭方式/DEC）；NOTES MUST NOT 作 stable must 源。
2. [[BEH-019]] / [[BEH-020]]：收口动作含同步 NOTES 头；partial 仍 exploring 时
   NOTES SHOULD 标明 partial。
3. `AGENTS.md` §6.2b/§6.2d、`poc/README.md`、`ndf_close.py` plan checklist 同步。
4. 回填已关闭且存在 NOTES 的主题头状态。

## 3. 冻结

`packages/ndf-harness/**` 零改动；统一重提炼另案。

## 4. 验收

- process 条款 + AGENTS + poc README + close plan 含 NOTES 要求
- 回填主题 NOTES 头含关闭 status
- `graphcheck --meta` hard_errors=0；harness 无变更
