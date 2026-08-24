# Proposal: POC 开题 TOPIC/DESIGN/INTERFACE 分段人工门禁 {#PROP-META-POC-DESIGN-REVIEW-GATES}

> track: process  
> Status: Implemented on 2026-08-11  
> 日期: 2026-08-11  
> 关联: [[BEH-025]], [[DEF-022]]  
> 场景: 装订器设计面串行人工审核后再实现  
> 原则: 只改 NDF 工作流；不改 `.openclaw/state.json`；不回填旧 POC

## 1. 动机

[[BEH-025]] 已要求 `DESIGN.md` / `INTERFACE.md`，但若一次写满三份即开码，用户无法
分段把关假设、软件设计与调用面。需要显式人工闸。

## 2. 决策

新开题 / 平级重启 MUST 串行：

1. 写好 `TOPIC.md` → 等用户 **`TOPIC已审核`** → 才写 DESIGN 正文  
2. 写好 `DESIGN.md` → 等用户 **`DESIGN已审核`** → 才写 INTERFACE 正文  
3. 写好 `INTERFACE.md` → 等用户 **`可以开始实现`** → 才委派/编写主题代码  

与产品提案的「已确认 / 已审核」口令分开，避免混淆。  
实质 amend TOPIC/DESIGN/INTERFACE 时，对应阶段重新过闸。  
模板 stub 可占位；「请审阅」仅在该文件可审后发出。  
历史缺文件仍仅工具 warning。

## 3. 非范围

- 不改 `.openclaw/state.json`  
- 不回填现有 POC；不改 bindcheck 硬错误策略；不蒸馏 harness  

## 4. 验收

BEH-025 + AGENTS / poc README / CLAUDE；`graphcheck --meta` hard_errors=0。
