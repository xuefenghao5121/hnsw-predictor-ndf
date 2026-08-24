# Proposal: bindcheck 对已入账 SHA 豁免 missing_trailer {#PROP-META-BINDCHECK-LEDGER-TRAILER}

> track: process  
> Status: Implemented on 2026-08-06  
> 日期: 2026-08-06  
> 关联: [[DEF-NDF-REPRO-BIND-GAP]], [[BEH-025]], GOVERNANCE 绑定面  
> 场景: 工具对齐 advise  
> 原则: 禁止 rewrite 已推送历史；Harness / state.json 不动

## 1. 动机

advise 沙盒对 `append_ledger_row` / banner 视 `missing_trailer` 为 mitigated，但
`ndf_bindcheck.check_bind` 仍无条件报硬错，与 GOVERNANCE「banner + ledger」不一致。

## 2. 决策

缺 `Topic:`/`Clauses:` 的 code commit，若其 short SHA **已出现在该 topic
COMMITS.md ledger**（code 或 ndf 列），则 **不发** `missing_trailer` error。
未入账的缺 trailer 仍报错。

## 3. 验收

装订器补行后 `bindcheck --all-topics` 对已入账历史 SHA 无 `missing_trailer`。
