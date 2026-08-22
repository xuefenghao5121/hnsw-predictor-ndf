# Proposal: POC 金标唯一绑定 + DELTA 逻辑空间 {#PROP-META-POC-GOLDEN-BIND-DELTA}

> track: process  
> Status: Implemented on 2026-08-11  
> 日期: 2026-08-11  
> 关联: [[META-007]], [[BEH-025]], [[META-006]], [[DEF-022]]  
> 场景: 开题唯一钉死金标 measure/cfg/bl；DELTA 跟踪功能与热点变化  
> 原则: 只改 NDF 工作流；不代填 POC/cfg/bl 实例；不改 `.openclaw/state.json`

## 1. 动机

四腿复现已定义，但开题仍可散文漂移；DESIGN/INTERFACE 管编码、PERF Numbers 管数字，
缺「功能怎么变 + 热点怎么移」的分解跟踪面。

## 2. 决策

1. **`DESIGN已审核` 之后、写 INTERFACE 之前**：MUST 写出 `PERF_BASELINE.md` **绑定头**
   （`vs` × `config_id` × `measure_script`/inherit；Numbers 可 pending R0）+ TOPIC
   `perf_baseline`；并写 `DELTA.md` 骨架  
2. **唯一绑定**：同主题一套对照金标身份；改绑 MUST 改头字段并在 DELTA 记一笔  
3. **DELTA.md**：Feature delta / Hotspot delta / Bind snapshot / 轮次表（非 SoT）  
4. 读序：TOPIC → DESIGN → PERF_BASELINE（绑定）→ DELTA → INTERFACE → …  
5. 工具：缺 `vs`/不可解析 cfg → error；缺 measure/DELTA → warning（历史）；show 打印三元组  

## 3. 非范围

- 不代填现有 POC；不改 state.json；不蒸馏 harness；不跑压测  

## 4. 验收

条款 + 模板 + AGENTS/poc/CLAUDE/golden-baseline 薄同步 + 工具；
`graphcheck --meta` hard_errors=0。
