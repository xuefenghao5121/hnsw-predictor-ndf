> track: poc
> topic: framework-driven-optimization
> Status: Implemented on 2026-08-09
> 日期: 2026-08-09

# 提案: 框架决策树驱动的系统性参数优化 — 256MB SIFT1M 1T

## 背景

DEC-087 的 EF=65 "2,483 QPS" 数据点经查为 cgroup 泄漏（pgmajfault=0, file_bytes=0），
严格 cgroup 下实际为 1,446 QPS。所谓"EF=65→70 QPS 断崖"是 cgroup 泄漏制造的假象。

DEC-088 调优框架已落地但引用了该错误数据点。本 POC 用框架决策树**系统性重扫**，
消除数据污染，找到 256MB SIFT1M 1T 下的真实最优。

## 依赖

- `depends_on_topics`: pipeline-param-retuning (promoted, DEC-087 数据待修正)
- `baseline_protocol`: [[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]] (sustained 金标)
- `baseline_trunk_sha`: 2e0ac9f (当前 Trunk tip)
- `methodology`: [[DEC-088]] 调优决策树

## 写入边界

- MUST NOT 修改 Trunk `src/`、`include/`、`tests/`
- 使用 Trunk `build/benchmark_sustained`（不改代码）
- 所有脚本在 `poc/framework-driven-optimization/` 下

## 实验计划（严格遵循 DEC-088 决策树）

### R0: 基线验证
- M=16 EF=100 1T 256MB, 验证 agg ≈ CON-SLA-020 的 1,076 ± 5%
- 同时作为 cgroup 有效性校验（pgmajfault > 0 才有效）

### R1: M_graph 扫描（决策树步骤 2）
- M=16 vs M=24, EF=100/80/60, 1T, 256MB
- 已有 results-strict/ 数据可复用（已验证 cgroup 有效）

### R2: EF 细扫（决策树步骤 3）
- 在最优 M_graph 上, EF = {50,55,60,65,70,75,80,90,100}
- 找 recall ≥ 95% 的最低 EF（真实拐点，不是 cgroup 泄漏假象）
- 记录 recall 余量

### R3: ADAPTIVE 评估（决策树步骤 4）
- 在 R2 最优 EF 上测试 ADAPTIVE（eef=40）
- 评估 recall 预算是否足够

### R4: 最优组合验证
- 完整 sustained benchmark (N=1000 R=15 seed=42)
- cgroup stats 验证（pgmajfault > 0）

## cgroup 有效性校验（新增）

每个 run 结束后 MUST 检查：
- `pgmajfault > 0`（证明发生了磁盘 I/O）
- `file_bytes > 0`（证明 page cache 在 cgroup 内积累）
- `violations = 0`（未触发 OOM）

pgmajfault=0 → 该 run 数据无效，标记并重跑。

## 自动化脚本

创建 `run_decision_tree.sh`，按决策树顺序执行，自动校验 cgroup，输出结构化结果。

> source: spec/decisions/24-tuning-framework.md (DEC-088) ; spec/decisions/26-fine-rerank-incremental-reject.md (cgroup 泄漏发现)
> track: poc ; Topic: framework-driven-optimization
