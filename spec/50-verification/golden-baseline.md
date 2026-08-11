# Golden Performance Baseline - Index

> 创建: 2026-08-09  
> 索引化: 2026-08-10（[[META-006]] / [[META-007]]；数字迁入 `baselines/`）  
> 最后更新: 2026-08-11（Config C 重新 k-means，恢复物理布局连续性）  
> 现行 Trunk 金标: **bl-trunk-golden-7ee4ee2**  
> 条款: [[CON-GOLDEN-001]]  
> 流程: [[META-006]], [[META-007]]

本文件是 **thin 导航**，不是数字 SoT。Agent / 压测对照 MUST 读下方指针。

## 现行金标

| 腿 | 身份 | 路径 |
|----|------|------|
| 代码 | `7ee4ee2b0af04feb154abcfd528feabe1557e073` | git |
| 配置 A/B/C | `cfg-sla-ef100` / `cfg-adaptive-ef90` / `cfg-m24-ef60` | [configs/](configs/) |
| 测量 | `scripts/run_golden.sh`（全量）/ `scripts/run_sustained.sh --config <id>`（单组） | [configs/](configs/) / [baselines/](baselines/) |
| 数字 | `bl-trunk-golden-7ee4ee2`（A/B/C 全 12 点, 2026-08-11） | [baselines/bl-trunk-golden-7ee4ee2.md](baselines/bl-trunk-golden-7ee4ee2.md) |

## 最佳性能速览（Config C: cfg-m24-ef60 + BEH-037 cluster sort, agg QPS）

| 场景 | agg QPS | steady QPS | Recall@10 |
|------|---------|-----------|----------|
| 256MB 1T | 1,747 | 1,917 | 96.60% |
| 256MB 16T | 5,218 | 6,929 | 96.60% |
| 512MB 1T | 2,154 | 2,519 | 96.59% |
| 512MB 16T | 8,698 | 16,341 | 96.59% |

> Config C + cluster sort 在全部场景均为最高 QPS；Config A (cfg-sla-ef100) recall 最高 (97.76%)。
> Config C 数据为重新 k-means 后结果（DEC-cluster-physical-layout）。
> ⚠️ 512MB 16T CV=6.0% 超标，后续补跑。

## 历史基线

| baseline_id | trunk | 日期 | 状态 | 说明 |
|-------------|-------|------|------|------|
| `bl-trunk-golden-434c6f5` | 434c6f5 | 2026-08-09 | superseded | 初始三配置金标 |
| `bl-trunk-golden-68059a6` | 68059a6 | 2026-08-10 | superseded | 仅 Config C, CQE peeking |
| `bl-trunk-golden-7ee4ee2` | 7ee4ee2 | 2026-08-11 | **current** | 全 12 点, BEH-036+037 |

## POC 读路径

1. `poc/<topic>/ndf/TOPIC.md` → `perf_baseline`
2. `poc/<topic>/ndf/PERF_BASELINE.md`（**唯一** `vs` × `config_id` × `measure_script` + Numbers）
3. `poc/<topic>/ndf/DELTA.md`（功能/热点分解；Bind snapshot 须与上表一致）
4. 卡内绑定 → 本目录 `baselines/` + `configs/` + 测量脚本

模板：
[baselines/PERF_BASELINE.topic-template.md](baselines/PERF_BASELINE.topic-template.md)、
`spec/meta/templates/poc/DELTA.md.stub`

## 使用规范

1. **Promote 后**：按 [[META-006]] 重跑 12 点，写入**新** `bl-trunk-golden-<shortsha>`，更新本索引与 [[CON-GOLDEN-001]] 指针
2. **配置变更**：新 `cfg-*`（或 POC experimental 全量 env）；MUST NOT 刷 [[CON-SLA-020]] 观测数字冒充新基线（[[META-007]]）
3. **A/B 对比**：同一 session 交替跑；CV > 3% 不可信
4. **回归**：相对现行 `bl-trunk-*`：±2CV / recall 0.3pp
5. **脚本**：`sudo bash scripts/run_golden.sh`
6. **工具**：`python3 spec/meta/tools/ndf_perf_baseline.py show --topic <id>`
   （装订校验；本目录只存 cfg/bl 数字与配置）
