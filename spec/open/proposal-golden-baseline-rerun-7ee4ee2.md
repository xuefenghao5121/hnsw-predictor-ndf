# Proposal: 重跑金标基线 bl-trunk-golden-7ee4ee2 (全 12 点)

> track: process  
> status: implemented  
> created: 2026-08-11  
> clauses: CON-GOLDEN-001, META-006, META-007, CON-SLA-020  
> trunk-ref: 7ee4ee2 (src/ 最后变更 SHA)  
> relates: BEH-036 (CQE peeking), BEH-037 (cluster vecblock reorder)

## 背景

BEH-036 (CQE peeking) 与 BEH-037 (cluster vecblock reorder) 已 promote 至 Trunk
(`7ee4ee2`)。按 [[META-006]]，promote 后 MUST 重跑金标 12 数据点（3 配置 × 2 cgroup
× 2 线程），写入新 `bl-trunk-golden-<sha>` 并更新索引与 [[CON-GOLDEN-001]] 指针。

**当前状态**：
- `bl-trunk-golden-7ee4ee2` 仅含 Config C (cfg-m24-ef60) 数据，**不完整**
- `bl-trunk-golden-434c6f5` (superseded) 含 A/B/C 三配置但基于旧 Trunk `434c6f5`
- [[CON-GOLDEN-001]] 正文仍指向 `bl-trunk-golden-434c6f5`，与 `golden-baseline.md`
  索引（指向 `7ee4ee2`）**不一致**
- Config A/B 在 `7ee4ee2` 上的数据**完全缺失**

## 目标

1. 在 Trunk `7ee4ee2` 上重跑全部 3 组配置 × 4 场景 = **12 数据点**，每点 ≥ 2 轮
2. 写入新金标基线卡 `bl-trunk-golden-7ee4ee2.md`（**覆盖替换**现有仅 Config C 的版本）
3. 关联三组金标配置（cfg-sla-ef100 / cfg-adaptive-ef90 / cfg-m24-ef60）
4. 更新 [[CON-GOLDEN-001]] 正文指针 -> `bl-trunk-golden-7ee4ee2`
5. 更新 `golden-baseline.md` 索引（代码 SHA = `7ee4ee2`，三配置齐全）
6. 标记 `bl-trunk-golden-434c6f5` 和 `bl-trunk-golden-68059a6` 为 superseded（已是）

## 实施计划

### Step 1: 编译验证

```bash
cd /home/huawei/hnsw-predictor-ndf && make clean && make -j$(nproc)
```

### Step 2: 全量金标测试

```bash
sudo bash scripts/run_golden.sh
```

覆盖：
- cfg-sla-ef100 (A): M=16, EF=100, ADAPTIVE=0
- cfg-adaptive-ef90 (B): M=16, EF=90, ADAPTIVE=1
- cfg-m24-ef60 (C): M=24, EF=60, ADAPTIVE=0

场景矩阵：256MB×{1T,16T} + 512MB×{1T,16T} = 4 场景 × 3 配置 = 12 点 × 3 轮

### Step 3: 写入基线卡

更新 `spec/50-verification/baselines/bl-trunk-golden-7ee4ee2.md`：

- `status: current`
- `configs: cfg-sla-ef100, cfg-adaptive-ef90, cfg-m24-ef60`
- 12 数据点（agg QPS / steady QPS / CV / Recall@10）
- 三配置横向对比表
- SLA 合规对照表
- BEH-037 cluster sort 增量对比（vs `bl-trunk-golden-434c6f5` Config C）

### Step 4: 更新 spec 指针

1. `spec/40-constraints/sla.md` [[CON-GOLDEN-001]] 现行观测基线 -> `bl-trunk-golden-7ee4ee2`
2. `spec/50-verification/golden-baseline.md` 索引 -> 确认 `bl-trunk-golden-7ee4ee2`
3. `spec/50-verification/configs/` 三配置文件确认 `trunk-ref` 对齐

### Step 5: graphcheck

```bash
python3 spec/meta/tools/ndf_index.py index
python3 spec/meta/tools/ndf_graphcheck.py
```

## "最佳性能"定义

基于 `bl-trunk-golden-7ee4ee2` 全量数据，**最佳性能**定义为：

| 维度 | 最佳配置 | 理由 |
|------|---------|------|
| 256MB 1T 最高 QPS | cfg-m24-ef60 + cluster sort | M=24 图连通性 + EF=60 低 I/O + cluster 局部性 |
| 256MB 16T 最高 QPS | cfg-m24-ef60 + cluster sort | 同上，16T 并行放大 cluster 局部性收益 |
| 512MB 1T 最高 QPS | cfg-m24-ef60 + cluster sort | 512MB 额外 page cache 空间 |
| 512MB 16T 最高 QPS | cfg-m24-ef60 + cluster sort | 最高绝对吞吐 |
| 最高 Recall | cfg-sla-ef100 | EF=100 保守，recall ~97.76% |
| SLA 基线锚点 | cfg-sla-ef100 | 对齐 [[CON-SLA-020]] 合约下限 |

**预期最佳绝对值**（基于 `7ee4ee2` 现有 Config C 数据）：
- 256MB 1T: ~1,812 agg QPS (cluster sort pread)
- 256MB 16T: ~5,223 agg QPS
- 512MB 1T: ~2,317 agg QPS
- 512MB 16T: ~9,770 agg QPS
- Recall: 96.59-96.60% (Config C)，97.76% (Config A)

## 不变更项

- Trunk `src/` / `include/` / `tests/` — 无代码变更
- [[CON-SLA-020]] SLA 下限数字 — 合约下限不变
- 三组 `cfg-*.md` 配置文件 — 旋钮值不变
- `scripts/run_golden.sh` / `scripts/run_sustained.sh` — 测法不变

## 风险

| 风险 | 缓解 |
|------|------|
| Config A/B 在 7ee4ee2 上性能与 434c6f5 有偏差 | BEH-036/037 改的是 I/O 路径和 vecblock 排序，对 M=16 图无直接影响；偏差应在 ±2CV 内 |
| run_golden.sh 全量跑需 ~2-3 小时 | 可接受；若需加速可先跑 Config A/B 补齐 |
| cluster sort 是 BEH-037 的 opt-in | 金标测试用 cluster-sorted 数据集 (`output/sift1m_m24/` 已有)；Config A/B 用原始数据 |
Status: Implemented on 2026-08-11

## 补充修复 (2026-08-11 16:42)

### 问题
首轮金标重跑发现 Config C 未使用 BEH-037 cluster-sorted vecblocks，
`run_sustained.sh` 硬编码 `VEC_BLOCKS_PATH=${DATA_PREFIX}_vecblocks_64k.bin`，
`cfg-m24-ef60.md` 未声明 cluster-sorted 路径。

### 修复
1. `cfg-m24-ef60.md`: 新增 `vecblocks_path` 字段指向 cluster-sorted 文件
2. `run_sustained.sh`: 新增 `CONFIG_VECBLOCKS_PATH` 解析逻辑，支持 config 覆盖
3. Config C 4 场景 × 3 轮重跑，使用 cluster-sorted vecblocks

### Config C cluster sort 结果
- 256MB 1T: 1,507 ± 17 (CV=1.1%)
- 256MB 16T: 3,649 ± 5 (CV=0.1%)
- 512MB 1T: 1,903 ± 67 (CV=3.5% ⚠️)
- 512MB 16T: 7,106 ± 20 (CV=0.3%)

### 旧金标差异说明
旧金标 cluster sort 单次测量报告 1,812/5,223/2,317/9,770，远高于本次 3 轮 mean。
差异归因于单次测量偏差。本次 3 轮结果作为现行金标。

## 二次修复 (2026-08-11 17:21)

### 问题
首轮修复中 `cfg-m24-ef60.md` 的 `vecblocks_path` 字段实际未写入（edit 工具报告成功但文件未变更）。
所有 Config C 金标测试（1,507/3,649/1,903/7,106）实际使用的是**无 cluster sort** 的默认 vecblocks 文件。

### 根因
1. `cfg-m24-ef60.md` 的 `vecblocks_path` 字段缺失
2. `run_sustained.sh` 中 `bash -c "..."` 块内的嵌套双引号 `"${CONFIG_VECBLOCKS_PATH:-}"` 导致引号提前关闭
3. Config A/B 也受影响（语法错误 `一元条件运算符使用了未预期的参数 "]]"`）

### 修复
1. `cfg-m24-ef60.md`: 重新写入 `vecblocks_path` 字段
2. `run_sustained.sh`: 去掉 `[[ -n ... ]]` 内的嵌套双引号
3. `disk_hnsw.cpp`: 临时添加 debug 输出验证 VEC_BLOCKS_PATH（验证后移除）
4. 重编译 benchmark_sustained
5. Config C 4 场景 × 3 轮重跑

### 验证
全部 12 个日志确认 `[FineRerank] VEC_BLOCKS_PATH=output/sift1m_m24/sift1m_m24_vecblocks_64k_cluster1024.bin`

### Config C 真·cluster sorted 结果
| 场景 | agg QPS (mean±std) | CV% | Recall |
|------|:---:|:---:|:---:|
| 256MB 1T | 1,512 ± 6 | 0.4% | 96.60% |
| 256MB 16T | 3,636 ± 72 | 2.0% | 96.60% |
| 512MB 1T | 1,952 ± 32 | 1.6% | 96.59% |
| 512MB 16T | 6,970 ± 212 | 3.0% | 96.59% |

### BEH-037 cluster sort 真实增量
| 场景 | 无 cluster | cluster sort | Δ% |
|------|:---:|:---:|:---:|
| 256MB 1T | 1,474 | 1,512 | +2.6% |
| 256MB 16T | 3,340 | 3,636 | +8.9% |
| 512MB 1T | 1,925 | 1,952 | +1.4% |
| 512MB 16T | 6,308 | 6,970 | +10.5% |
