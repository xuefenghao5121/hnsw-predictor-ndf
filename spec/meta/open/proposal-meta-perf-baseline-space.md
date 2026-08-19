# Proposal: 收口黄金基线 — Agent 可读性能线 {#PROP-META-PERF-BASELINE-SPACE}

> track: process  
> Status: Implemented on 2026-08-10  
> 日期: 2026-08-10  
> 关联: [[META-006]], [[BEH-025]], [[CON-POC-001]], [[CON-GOLDEN-001]]  
> 场景: 金标拆库 / POC 性能线读路径  
> 原则: 延续黄金三要素；不另起平行真理；配置-only 须有 cfg 身份

## 1. 动机

[[CON-GOLDEN-001]] / `golden-baseline.md` / [[META-006]] 本意已是锁定
**代码 SHA × 配置 × 数字**。缺口是：配置无稳定 `cfg-id`；POC TOPIC 不强制接到金标卡；
Agent 常从 CON-SLA / NOTES 抄观测数字，配置-only 时去刷 SLA。

## 2. 决策

1. 在 `spec/50-verification/` 拆 **configs/** + **baselines/**（迁出现有黄金内容）；
   `golden-baseline.md` 改为 thin 索引。
2. [[CON-GOLDEN-001]] 指针化到 `cfg-*` / `bl-trunk-*`。
3. [[META-006]] 更新目标改为写 configs/baselines + 薄索引；禁止只改 `sla.md` 观测数字。
4. 新 [[META-007]]：Agent 读写义务；配置-only 须换/写清 cfg 并重测；SLA ≠ 性能线。
5. [[BEH-025]]：R0 后 MUST `perf_baseline` → `ndf/PERF_BASELINE.md`；比 Δ% 只读该卡。
6. 工具：`spec/meta/tools/ndf_perf_baseline.py`（装订门禁，非 SLA 业务）；AGENTS / CLAUDE / poc README 薄同步。

## 3. 非范围

不回填全部历史关闭 TOPIC；不做内容寻址；不自动从 CSV 生成卡；不动 Harness / state.json。  
**落点**：`ndf_perf_baseline.py` 在 `spec/meta/tools/`（流程装订校验，同 bindcheck 族）；  
产品数字/配置仍在 `spec/50-verification/{configs,baselines}/`。

## 4. 验收

条款 + registry + 样板 TOPIC 卡 + 工具；`graphcheck --meta` hard_errors=0。
