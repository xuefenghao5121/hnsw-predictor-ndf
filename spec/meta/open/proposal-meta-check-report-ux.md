# Proposal: 检查报告落点与可读性 {#PROP-META-CHECK-REPORT-UX}

> track: process  
> Status: Implemented on 2026-08-06  
> 日期: 2026-08-06  
> 关联: [[BEH-026]], GOVERNANCE 派生物层  
> 场景: 规范卫生 / 工具链  
> 原则: 报告非 must；禁污染 `spec/open/`；Harness 冻结

## 1. 动机

`ndf_graphcheck` / `ndf_bindcheck` 报告曾被写入 `spec/open/`（提案入口），且每条
issue 重复整图 mermaid，审核无法扫读。GOVERNANCE 已规定派生物落 `tmp/*`，工具未强制。

## 2. 决策

1. `--report` 默认 `tmp/ndf-graphcheck.md` / `tmp/ndf-bindcheck.md`（相对仓库根）；
   `--report -` 仅 stdout。
2. 解析后路径若落在 `spec/` 下 → exit 2（含 `open/`、`meta/open/`、`archive/`）。
   允许仓库 `tmp/` 与 OS `/tmp/...`。
3. 报告版式：Dashboard + Issue index 表 + 按 kind（bind 按 topic）一张聚合图；
   `--detail` 才展开逐条 hop/长文；ledger 二部图进 Appendix。
4. 写报告时 stdout 仅短摘要；删除误写入 `spec/open/` 的旧报告。
5. README / GOVERNANCE 示例统一 `tmp/...`，明示 MUST NOT 写入 `spec/open/`。

## 3. 冻结

`packages/ndf-harness/**` 零改动；统一重提炼另案。

## 4. 验收

- 写入 `spec/open/*.md` 被拒绝；默认写入 `tmp/`
- 新报告含 Issue index 表与聚合 mermaid，无默认逐条大图
- `spec/open` 无 graphcheck/bindcheck 报告残留
