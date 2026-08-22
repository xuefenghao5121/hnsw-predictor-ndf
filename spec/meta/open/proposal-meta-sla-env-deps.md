# Proposal: META trunk-ref + 性能 SLA↔API 图依赖纪律 {#PROP-META-SLA-ENV-DEPS}

> track: process  
> Status: Implemented on 2026-08-06  
> 日期: 2026-08-06  
> 关联: [[META-001]], [[META-002]], [[META-005]], [[BEH-019]], [[BEH-025]], [[ADR-META-002]]  
> 场景: 规范卫生 / 元语言  
> 原则: 产品无关正文；不写具体 env 名

## 1. 动机

Trunk 性能 SLA 与旋钮接口仅靠散文配置串，无法图检；亦缺可复现的 git SHA/tag 绑定。
POC 已有 `baseline_trunk_sha`；产品侧需要对等的自由元数据键。

## 2. 决策

1. **[[META-001]]**：登记自由元数据字段 `trunk-ref`（非图边）：
   - 推荐完整 40-char SHA；允许可 `rev-parse` 的 tag（正文 SHOULD 再写解析 SHA）
   - 与 `since`/`source`/`topic` 同类；**不**进入 [[META-002]] 结构边键表
2. **新增 [[META-005]]**（`language.md`）：
   - Trunk **stable** 且含测量配置的性能 SLA MUST `depends-on` 声明其旋钮的 API 条款（及必要行为条款）；仅正文 env 串不够
   - 上述 SLA 与对应 API MUST 带 `trunk-ref=`
   - 默认值 MUST 对应该 ref 的 Trunk 树（`source=observed`）；测量配置另列，MUST NOT 把测量值写成默认
   - promote/partial 收口 SHOULD 更新相关 API·SLA 的 `trunk-ref`（与 [[BEH-019]] 同闸笔记；close plan 可点一句）
3. **不**把缺 `trunk-ref` 做成 graphcheck hard error（本轮；follow-up）

产品侧 DEF-024 / API / SLA 回填见 `spec/open/proposal-sla-env-graph.md`（另案 track=bug）。

## 3. 验收

- `ndf_graphcheck.py --meta` hard_errors=0
- META-001 表含 `trunk-ref`；META-005 入 INDEX / `ndf.yaml` layout
