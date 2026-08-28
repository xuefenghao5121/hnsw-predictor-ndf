# 组合调优器（rp-optuna-tuner）

> 离线设计空间探索（DSE）工具。条款：[[BEH-029]]、[[ARCH-010]]、[[API-014]]、[[DEC-005]]
> 语义核：`spec/models/rp-optuna-tuner.md`
> track: promote ; Topic: rp-optuna-tuner
> source: poc/rp-optuna-tuner/ndf/TOPIC.md ; spec/open/proposal-promote-rp-optuna-tuner.md @ 95fe56d

组合调优器在已晋升的约束感知调优器（`tools/constraint-aware-tuner/`，[[BEH-028]] /
[[ARCH-009]]）之上，组合三级先验做**离线**超参数搜索：

1. **搜索先于重建**（DiskANN-Autotuner 式）：固定 artifact 上先校准 `REFINE_EF` 下限 +
   per-artifact GBDT 重训，再决定是否花重建预算。
2. **RP-Tuning 后置 RobustPrune(α₂)**（arXiv:2602.08097v1）：在够密的基图上做图重写 pass，
   把 α/密度轴从「每 α 一次完整 Vamana 重建」便宜化成 0-rebuild。
3. **Optuna TPE 剩余重建轴**：RP 覆盖不了的轴（block 阶梯 / pq_M）交给 TPE ask-and-tell，
   每 trial = 一次完整重建，recall ≥95% 是**硬约束**而非 soft loss。

它**不进入查询热路径**：RobustPrune 是离线图重写 pass，Optuna 是离线求解器，二者 MUST NOT
编进 `disk_hnsw` 查询。与 `traverse.py`（CAT 嵌套遍历）是**互补**而非替换——CAT 仍可用，本工具
补 RP α/密度 0-rebuild 与 Optuna 剩余重建轴。

> ⚠️ 本文档中的 POC evidence 数字只是**引用**（探索阶段实测），**不是** stable must SLA。
> 承诺的 SLA 数字以 `spec/50-verification/` 的 `[[META-006]]` 重测金标为准（[[CON-POC-001]]）。

## 入口

```bash
# 廉价剪枝 / 图重写自检（无 build / 无测量）
make -C tools/rp-optuna-tuner/harness
tools/rp-optuna-tuner/harness-bin/tune_main --self-test
tools/rp-optuna-tuner/harness-bin/robust_prune_main --help

# Optuna 薄驱动自检（无测量）
python3 tools/rp-optuna-tuner/optuna/optuna_driver.py --self-test

# 搜索先于重建：ef 下限 + per-artifact GBDT 重训校准（0 rebuild）
python3 tools/rp-optuna-tuner/harness/calibrate_s0.py --self-check   # 环境自检
python3 tools/rp-optuna-tuner/harness/calibrate_s0.py --ef-floor     # 只测 ef 下限
python3 tools/rp-optuna-tuner/harness/calibrate_s0.py                # ef 下限 + GBDT 重训

# RP 密基图（1 rebuild）+ Optuna 剩余轴（每 trial 1 rebuild）
bash tools/rp-optuna-tuner/scripts/build_rptbase.sh    # RP 基图（beam=64/α=1.2）
python3 tools/rp-optuna-tuner/harness/run_s3_optuna.py # Optuna TPE 打 block×pq_M
```

测量**改接 Trunk**：`build_rptbase.sh` 委托 `scripts/build_pipeline.sh`，`run_rp_sustained.sh`
委托 `scripts/run_sustained.sh`（[[VER-001]] / [[VER-003]]），**不携带独立搜索引擎**。唯一的
例外是 `run_gbdt_probe.sh` 的 per-artifact GBDT on-leg，它用
`tools/rp-optuna-tuner/harness-bin/benchmark_sustained_poc`（对 `disk_hnsw_llsp.cpp` 的薄
instrument 拷贝 + per-artifact 模型头），因为该模型 MUST NOT 覆盖 Trunk `include/gbdt_model.h`
（[[BEH-029]]）。

## 推荐流水线（预算分配）

以金标锚点起步（不耗预算）。括号内为 rebuild 数：

| 阶段 | rebuild | 内容 |
|------|---------|------|
| S0 搜索侧校准 | 0 | 固定默认图（beam=64/α=1.2）上实测 `REFINE_EF` 下限 + per-artifact GBDT 重训 |
| S1 密基图 | 1 | 建 beam=64/α=1.2 密基图（RP 基图），复现/超越金标工作点 |
| S2 RP α₂ 阶梯 | 0 | 在 S1 基图上后置 `RobustPrune(α₂)` 图重写（可选） |
| S3 Optuna 剩余轴 | ≤11 | TPE 打 block 阶梯 × pq_M；每 trial 1 rebuild + ef floor + GBDT 重训 |

**停止规则**：`RPT_BUDGET_REBUILDS` 耗尽即停；或当前最优相对金标无改善即停。**任何一步重建后
MUST 先重实测该图的 ≥95% ef 下限 + GBDT 校准，再比 QPS**。

## 硬约束

- recall ≥95%（sustained，512MB cgroup；目标 ≥95.5% guard 以抗测量噪声擦线）。
- 可行性 MUST 纳入 cgroup 内存预算（[[CON-001]]）+ sustained 协议（[[VER-001]]/[[VER-003]]）。
- RP 后置 prune **不等于**免 VER：RP 产物 MUST 重新 sustained（[[BEH-029]]）。
- 每张新图 MUST 重训 GBDT；禁止跨图复用 `include/gbdt_model.h`（[[BEH-029]]）。
- Optuna MUST NOT 把 cgroup/recall 硬约束折成标量 soft loss（[[BEH-029]]）。
- MedianPruner 只用于廉价内层（ef floor / RSS proxy），禁止剪一半的 sustained。

## 旋钮

| 旋钮 | 默认 | 语义 |
|------|------|------|
| `RPT_BUDGET_REBUILDS` | 14 | 完整 Vamana insert 重建预算上限（RP 图重写 / GBDT 重训不计） |
| `RPT_BASE_GRAPH` | beam=64/α=1.2 | RP 基图（M=16/R0=40/Rup=16/rounds=3/seed=42/256KB） |
| `RPT_ALPHA2_LADDER` | [1.2,1.1,1.0,0.9,0.8] | 后置 RobustPrune α₂ 阶梯（每 α₂ 一次图重写，0 rebuild） |
| `RPT_BLOCK_SIZE` | 262144（256K） | block 阶梯 {32768,65536,131072,262144}（2 的幂 × 4096 对齐） |
| `RPT_PQ_M` | 64 | PQ 子空间 M（finest 压 ef 下限） |
| `RPT_OPTUNA_SAMPLER` | TPE | Optuna 采样器（TPE / CMA-ES） |
| `RPT_OPTUNA_N_TRIALS` | ≤11 | Optuna trial 预算（= 14 − 3 已耗 S1+H2） |
| `RPT_CGROUP_MB` | 512 | cgroup 内存预算（[[CON-001]]） |
| `RPT_THREADS` | 16 | 测量线程数（1T 补充） |
| `RPT_REFINE_EF` | 40 | 搜索侧 ef（固定 artifact 上先校准） |
| `RPT_RECALL_FLOOR` | 0.95 | recall 硬约束 |
| `RPT_GBDT_RETRAIN` | 0 | per-artifact GBDT 重训管线 flag（probe 通过后置 1） |
| `GBDT_MARGIN` | 1.3 | LEARNED_EF margin 乘子（工作点耦合量，非 outer-grid 旋钮） |

`RPT_*` → `HV_*` 映射复用 `build_index`（[[API-011]] / [[API-014]]）。

## 改接 Trunk 测量

`cfg-sla-ef100` 钉死默认图（`output/sift1m`）+ winner vecblocks。调优器要测**非默认** artifact
（RP 基图 / RP 剪枝图）时，用 `run_rp_sustained.sh` 显式传 `DATA_PREFIX` / `VEC_BLOCKS_PATH` /
`PQ_CODES_PATH`（绕开 cfg 的 vecblocks 硬钉）：

```bash
# 默认图（走 cfg-sla-ef100，REFINE_EF=40 / pq_M=64 / LEARNED_EF=1 GBDT_MARGIN=1.3）
CGROUP_MB=512 THREADS=16 bash scripts/run_sustained.sh --config cfg-sla-ef100

# 非默认 artifact（RP 基图 / RP 剪枝图）
CGROUP_MB=512 THREADS=16 EF=40 BS=262144 \
  DATA_PREFIX=output/sift1m_rptbase \
  VEC_BLOCKS_PATH=output/sift1m_rptbase_vecblocks_256k.bin \
  PQ_CODES_PATH=output/pqco_sift1m_M64.bin \
  EXTRA="export LEARNED_EF=1 GBDT_MARGIN=1.3" \
  bash tools/rp-optuna-tuner/scripts/run_rp_sustained.sh
```

## S2 结论（避免误用）

- **RP 不便宜化 block / PQ_M / BFS reorder**：它只把 α/密度轴（每 α 一次重建）变成图重写 pass。
- **后置 prune 更稀 → ef 下限升高 → QPS 下降**：RP 不改善相对密基图的 QPS；α₂<1.0 处 recall 掉崖
  （α₂=0.95 起 infeasible）。
- **生产默认用密基图（α₂=1.2 幂等），不用 α₂<1.0**。RP 后置 prune 不当默认生产 pass。

## S3 结论

- block 阶梯单调：256K > 128K > 64K > 32K（cache slots 塌缩）。
- `pq_M=64`（finest PQ）把 ef 下限从 50 压到 40（pq_M=16 粗 PQ 反升到 90）。
- GBDT margin 全景（pq_M=64）：m=1.0 贴 95% floor（95.46% < 95.5% guard），报告/默认工作点
  取 m=1.3。

## 安装与依赖

- **Optuna**（Tuner 的 Python 依赖，仅 TPE/CMA-ES ask-and-tell）：`pip install optuna`。
  Optuna 缺省时 `optuna_driver.py` 退化为确定性 closed-ladder（仍跑通硬约束路径）。
  MUST NOT 把 Optuna 源码 vendor 进 `src/`，MUST NOT 进查询热路径。
- **LightGBM**（GBDT 重训）：`pip install lightgbm`。
- 编译：`make -C tools/rp-optuna-tuner/harness`（g++ -O3，`-I` 指向 Trunk `include/` /
  `hnswlib/`，复用 Trunk `src/core/{block_cache,graph_prefetcher}.cpp`）。

## 失败模式

| 症状 | 处理 |
|------|------|
| RP 后 recall 掉崖 | 记录失败模式；回退到该 α₂ 完整重建对照（H2 证伪/证实） |
| Optuna 提议 RSS 不可行 | 剪枝器拦下；记录 |
| 新图 GBDT 仍无余量（贴 95% floor） | skip gate #2（P75 min_n ≈ 候选表封顶）；不否定现行金标 |
| 剪枝误剪可行配置 | 搜索预算内回退到完整 build 校验 |
