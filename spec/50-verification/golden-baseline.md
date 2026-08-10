# Golden Performance Baseline — Index

> 创建: 2026-08-09  
> 索引化: 2026-08-10（[[META-006]] / [[META-007]]；数字迁入 `baselines/`）  
> 现行 Trunk 金标: **bl-trunk-golden-68059a6**  
> 条款: [[CON-GOLDEN-001]]  
> 流程: [[META-006]], [[META-007]]

本文件是 **thin 导航**，不是数字 SoT。Agent / 压测对照 MUST 读下方指针。

## 现行金标

| 腿 | 身份 | 路径 |
|----|------|------|
| 代码 | `434c6f5874a27c64c26a973f28988d90159e06a3` | git |
| 配置 A/B/C | `cfg-sla-ef100` / `cfg-adaptive-ef90` / `cfg-m24-ef60` | [configs/](configs/) |
| 测量 | `measure_script` / `measure_binary`（cfg 或 bl 头字段；人工维护） | [configs/](configs/) / [baselines/](baselines/) |
| 数字 | `bl-trunk-golden-68059a6` | [baselines/bl-trunk-golden-434c6f5.md](baselines/bl-trunk-golden-434c6f5.md) |

## POC 读路径

1. `poc/<topic>/ndf/TOPIC.md` → `perf_baseline`
2. `poc/<topic>/ndf/PERF_BASELINE.md`（主题性能线卡；含 **Measure**）
3. 卡内 `vs:` / `config_id` / `measure_script` → 本目录 `baselines/` + `configs/`

模板：[baselines/PERF_BASELINE.topic-template.md](baselines/PERF_BASELINE.topic-template.md)

## 使用规范

1. **Promote 后**：按 [[META-006]] 重跑 12 点，写入**新** `bl-trunk-golden-<shortsha>`，更新本索引与 [[CON-GOLDEN-001]] 指针
2. **配置变更**：新 `cfg-*`（或 POC experimental 全量 env）；MUST NOT 刷 [[CON-SLA-020]] 观测数字冒充新基线（[[META-007]]）
3. **A/B 对比**：同一 session 交替跑；CV > 3% 不可信
4. **回归**：相对现行 `bl-trunk-*`：±2CV / recall 0.3pp
5. **脚本**：`sudo bash scripts/run_golden.sh`
6. **工具**：`python3 spec/meta/tools/ndf_perf_baseline.py show --topic <id>`
   （装订校验；本目录只存 cfg/bl 数字与配置）
