# 约束感知调优器（constraint-aware-tuner）

> 离线设计空间探索（DSE）工具。条款：[[BEH-028]]、[[ARCH-009]]、[[API-013]]、[[DEC-004]]
> 语义核：`spec/models/constraint-aware-tuner.md`
> track: promote ; Topic: constraint-aware-tuning
> source: poc/constraint-aware-tuning/ndf/TOPIC.md ; spec/open/proposal-promote-constraint-aware-tuning.md @ d9122d2

约束感知调优器是 DiskHNSW 的**离线**超参数调优工具：用「结构感知搜索 + 廉价可行性剪枝 +
实测校验」在远少于 grid / Optuna 的完整 rebuild 次数内，找到满足 recall ≥95%（cgroup /
sustained 口径）且优于锁定默认 QPS 的配置。它**不进入查询热路径**。

> ⚠️ 本文档中的 POC evidence 数字只是**引用**（探索阶段实测），**不是** stable must SLA。
> 承诺的 SLA 数字以 `spec/50-verification/` 的 `[[META-006]]` 重测金标为准（[[CON-POC-001]]）。

## 入口

```bash
# 用户主入口：P0–P4 嵌套遍历（build + sustained 测量）
python3 tools/constraint-aware-tuner/scripts/traverse.py

# 廉价剪枝自检（无 build / 无测量）
python3 tools/constraint-aware-tuner/scripts/traverse.py --self-test
g++ -O2 -std=c++17 -Itools/constraint-aware-tuner \
    -o /tmp/tune_main tools/constraint-aware-tuner/harness/tune_main.cpp
/tmp/tune_main --self-test
```

`traverse.py` 复用 Trunk `scripts/build_pipeline.sh` + `scripts/run_sustained.sh` /
`benchmark_sustained`（[[VER-001]] / [[VER-003]]），**不携带独立搜索引擎**。

## 六条耦合（为什么不能独立扫单旋钮）

调优空间里的旋钮不是独立的，存在六条一阶耦合（DESIGN §0）：

| 耦合 | 含义 | 后果 |
|------|------|------|
| ef ↔ graph | recall 同时取决于 `REFINE_EF` 与图结构 | 换图后必须重测 ef 下限 |
| ef ↔ block/layout | ef 下限随切块布局移动 | 换 block 后重测 ef |
| graph-pack ↔ block | 图打包与块尺寸交互 | block 影响图邻接的磁盘局部性 |
| 4KB 页 ↔ block | block 必须 4KB 对齐 | block 非 4096 倍数 → 页粒精排退化 |
| RSS/cgroup ↔ block | 内存预算约束块缓存 slots | block 越大 → slots 越少 |
| PQ_M ↔ rerank ↔ ef | PQ 质量耦合精排与候选数 | pq_M 改变 → ef 下限与 QPS 联动 |

因此搜索是**嵌套 / 坐标下降 + 重入**，不是一次网格或三阶段孤立扫描。

## P0–P4 顺序

| 阶段 | rebuild | 内容 |
|------|---------|------|
| P0 | 0 | 锁定默认图 + 64KB，实测 ef 阶梯（QPS/recall 基线） |
| P1 | 3 | block 阶梯 {32K,128K,256K}，每个重测 ef 下限，选 B* |
| P2 | ≤6 | 在 B* 上坐标下降：R0 {40,48} → beam {48,64} → α {1.33,1.07}，选 G* |
| P3 | ≤3 | 图改变则重入 block 阶梯（预算允许时） |
| P4 | ≤4 | 残余预算：pq_M {16,64}（仅预算剩余时） |
| GBDT probe | 0 | 可选 per-artifact 搜索侧校准（见下），**不计** rebuild 预算 |

内层（0 rebuild）在固定图+布局上**二分实测 ≥95% 的 `REFINE_EF` 下限**（工作点）；先验只用于
**完整 build 前剪枝**，绝不当报告工作点。

## 旋钮

| 旋钮 | 默认 | 语义 |
|------|------|------|
| `CAT_BUDGET_REBUILDS` | 16 | 完整 rebuild 预算上限（GBDT 探针不消耗） |
| `CAT_GBDT_PROBES` | 1 | 可选 GBDT 探针 artifact 上限（max 2，不计 rebuild） |
| `CAT_BLOCK_SIZE` | 65536 | block 阶梯 {32768,65536,131072,262144}（2 的幂 × 4096 对齐） |
| `CAT_PQ_M` | 32 | PQ 子空间 M |
| `CAT_CGROUP_MB` | 512 | cgroup 内存预算（[[CON-001]]） |
| `CAT_THREADS` | 16 | 测量线程数（1T 补充） |
| `CAT_ENABLE_GBDT` | 0 | GBDT 可选轴开关（`LEARNED_EF` 透传，默认关） |

建图旋钮 `CAT_*` → `HV_*` 映射复用 `build_index`（[[API-011]]）。

## 与 grid / Optuna 的差别

| | grid | Optuna-like | 本工具 |
|--|------|-------------|--------|
| 搜索方式 | 全笛卡尔积 | 黑盒随机 / 贝叶斯 | 结构感知嵌套 + 坐标下降 |
| rebuild 次数 | ~1008（代表空间） | ~336（~grid/3） | **14/16** |
| 结构先验 | 无 | 无 | ef 单调 / α 单峰 / 可分离资源模型 |
| 内存可行性 | 事后发现 | 事后发现 | **build 前剪枝**（cgroup 预算） |

## 配置记录（[[VER-004]]）

调优产出的最优配置以配置记录形式落地（`spec/50-verification/configs/cfg-<id>.md`），记录完整
旋钮 / 环境（`TWO_STAGE`、`FINE_*`、`CACHE_MB`、`FLAT_VEC_MB`、`REFINE_EF`、线程、cgroup）。
不侵入 Trunk 默认，不复制 POC QPS 进 stable SLA（[[CON-POC-001]]）。

## GBDT 可选探针

搜索默认 `LEARNED_EF=0`（[[BEH-010]]）。调优器内可选 per-artifact GBDT 探针
（`tools/constraint-aware-tuner/scripts/run_gbdt_probe.sh`）受三道 skip gate 控制：

1. **skip gate #1**：余量 `floor_recall − 95%` ≲ 1pp → 跳过（winner 95.57% = +0.57pp 即跳过）。
2. **skip gate #2**：P75 min_n 卡在候选表封顶（≈ floor_ef）→ 无 headroom，跳过。
3. **skip gate #3**：sim margin sweep 仅 ≥95% 者进入 sustained。

模型按 artifact 生成（`tools/constraint-aware-tuner/harness/gbdt_model_<id>.h`），MUST NOT
覆盖 Trunk `include/gbdt_model.h`，MUST NOT 跨图复用模型头。
