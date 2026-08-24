# Proposal: 性能线测量脚本绑定 {#PROP-META-PERF-MEASURE-SCRIPT}

> track: process  
> Status: Implemented on 2026-08-10  
> 日期: 2026-08-10  
> 关联: [[META-006]], [[META-007]], [[BEH-025]]  
> 场景: 性能线第四腿 — measure（可执行入口）  
> 原则: 只改 NDF 工作流；cfg/bl/POC 卡具体路径由人工回填

## 1. 动机

[[META-007]] 已钉 SHA × 配置 × 数字，但 Agent 仍不知「用哪个脚本、哪个 binary 跑出这些数」。
产品 VER-043 有复现块，未接到性能线卡契约。

## 2. 决策

**四腿复现**：`trunk_sha` × `config_id` × `measure` × `numbers`

1. PERF_BASELINE 正文 MUST 含 **Measure** 节（或显式 inherit cfg 并链到 cfg）
2. 头字段：`measure_script` / `measure_binary`（repo 或 topic 相对路径）；可选 `verifies:` 薄指针 VER
3. cfg / bl 产品验证树 **MAY** 在同名字段记录测量入口（人工维护）
4. [[META-007]]：比性能前 MUST 读到 Measure；缺绑定 = 性能线不完整（工具对未回填 topic 先 warning）
5. COMMITS ledger **MAY** 增 `measure_script` 列
6. 扩展 `ndf_perf_baseline.py` 校验 Measure 节与路径存在性

## 3. 非范围

- 不代填 cfg/bl/POC 实例、不改 `scripts/`  
- 不新建 VER 正文  
- 不动 packages/ndf-harness（蒸馏另案）

## 4. 验收

条款 + 模板 + README 索引 + 工具；`graphcheck --meta` hard_errors=0。
