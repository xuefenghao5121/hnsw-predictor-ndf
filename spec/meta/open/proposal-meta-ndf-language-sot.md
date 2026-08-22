# Proposal: Meta 内 NDF 原始语言 SoT {#PROP-META-NDF-LANGUAGE-SOT}

> track: process  
> Status: Implemented on 2026-08-05  
> 日期: 2026-08-05  
> 关联: [[ADR-META-001]], [[ADR-META-002]], [[DEF-META-ID-NS]], [[DEF-NDF-GRAPH]], [[META-001]], [[META-002]], [[META-003]]  
> 场景: 规范卫生 / 元分层  
> 原则: NDF 语言 SoT 在本地 `spec/meta/`；上游 normative_language 非 SoT；不改产品节点

## 1. 动机

`spec/meta/` 有流程与图缺陷词典，但缺少「何为 NDF 条款」的本地可审计定义；仅靠外链与工具实现惯例。

## 2. 决策

1. 新增 [`spec/meta/language.md`](../language.md)：`{#META-001}`…`{#META-003}`（产品无关）。
2. `meta/README.md`、`spec/README.md`、`ndf.yaml` layout 登记；[[DEF-NDF-GRAPH]] 依赖语言条款。
3. 上游 [normative_language](https://github.com/hengliao1972/normative_language) 标为非 SoT 参考。
4. 不改产品 `00–50`；本轮不同步 Harness。

## 3. 验收

- `language.md` 可回答骨架 / 元数据 / 边键 / 分层语气
- `ndf_graphcheck.py --meta` hard_errors=0；META-001… 入 `meta/INDEX.md`
- 产品条款零 diff
