# Proposal: 严格隔离基线语义固化（DEC-066 补全） {#PROP-STRICT-BASELINE-SEMANTICS}

> track: process
> Status: Implemented on 2026-08-03
> 日期: 2026-08-03
> 关联: [[DEC-065]], [[DEC-066]], [[CHR-006]], [[CON-SLA-011]], [[CON-SLA-014]], [[VER-039]], [[CON-SLA-008]], [[CON-SLA-013]]
> 场景: 规范卫生 / 基线确立后闭环

## 动机

用户确认：[[CON-SLA-014]] 严格隔离是当前最合理、符合需求的测试方法；
2026-08-03 SIFT1M 数字是后续优化的**对齐基线**，不是白嫖 era 的 must QPS 复活。

审查发现需补全：
1. must 门槛 vs 观测基线语义分离
2. 4T RSS 实测超旧 ≤300MB
3. 旧 ≥2000/≥100 残留
4. `DEC-066` ID 与 io-behavior 提案预留冲突 → pipe amend 改用 DEC-067+

## 决策（落地）

| 项 | 处理 |
|----|------|
| QPS | **观测对齐基线**（非 must 点承诺）；回归 should ≥ 基线×0.9 |
| Must | Recall≥95%、CON-SLA-014、oom=0、peak≤limit、RSS 分线程 |
| RSS | 1T ≤300MB；4T ≤450MB（锚定实测 416/426） |
| 残留 | CON-SLA-008 / VER-030 / CON-SLA-013 / CON-SLA-014 文案 |
| pipe POC | `proposal-io-behavior-correction` 预留 ID → **DEC-067** |
