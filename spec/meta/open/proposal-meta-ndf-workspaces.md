# Proposal: NDF 三工作空间本体定义 {#PROP-META-NDF-WORKSPACES}

> track: process  
> Status: Implemented on 2026-08-12  
> 关联: [[META-003]], [[BEH-025]], [[META-007]], [[DEF-NDF-GRAPH]]  
> 原则: 三空间是 NDF 的正交工作视角；交互属于编排，不建平行文件系统

## 决策

1. 新增 [[META-008]]：定义设计、实现、测试空间与现有 L0–L3、树/图/git 的多对多关系。
2. 图是规范依赖 IR；上下文由任务意图、装订器读序、图展开及 git/evidence 共同组装。
3. 测试区分比较/决策 SoT 与审计/复现证据；冲突 MUST 复测或以 DEC/提案裁决。
4. `DELTA` 是设计↔测试变化账本，不是第四空间；交互编排不替代三空间真值。

## 非范围

- 不增加口令或 mandatory 装订器文件
- 不代填既有 POC；不改 `.openclaw/state.json`；不蒸馏 harness

## 验收

META-008、术语、模板与读序薄同步；`graphcheck --meta` hard_errors=0。
