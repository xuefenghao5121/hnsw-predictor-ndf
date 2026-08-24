# Proposal: bindcheck 装订器卫生（双头 + ledger 补行） {#PROP-FIX-BINDCHECK-BINDER-HYGIENE}

> track: bug  
> Status: Implemented on 2026-08-06  
> 日期: 2026-08-06  
> 关联: [[DEF-NDF-BINDER-DUAL-HEAD]], [[DEF-NDF-REPRO-BIND-GAP]], PROP-META-BINDCHECK-LEDGER-TRAILER  
> 场景: 装订器卫生；仅 `poc/*/ndf/`  
> 原则: 不 amend git；不改 `src/` / state.json / Harness

## 1. 变更

1. **双头**：cgroup TOPIC 将 BEH-032/API-016（及 DEC-079）移出 Draft；l4 将 BEH-024 标为 promoted/stable。
2. **ledger**：为缺 trailer 的历史 SHA 追加 COMMITS 行（见计划表）；缺 banner 的 topic 补 not-backfilled。
3. **warning**：fine-rerank 孤儿 draft 标 rejected；multi-thread TOPIC 登记 API-013/BEH-027。

## 2. 验收

`ndf_bindcheck.py check --all-topics --report tmp/ndf-bindcheck.md` → hard_errors=0。
