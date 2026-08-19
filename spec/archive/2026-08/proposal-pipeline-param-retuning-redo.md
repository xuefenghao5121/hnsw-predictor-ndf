> track: poc
> topic: pipeline-param-retuning
> status: proposal (amendment)
> 日期: 2026-08-08

# 提案: 重做 pipeline-param-retuning POC - 对齐金标配置 + DEC-086 最优基线

## 问题

pipeline-param-retuning POC 的全部实验（R0–R5）存在两个基线问题：

### 问题 1: 测试脚本缺少 CON-SLA-020 必需 env 变量

| 环境变量 | CON-SLA-020 规定 | R0–R5 实际 | 影响 |
|----------|-------------|-----------|------|
| `L4_WILLNEED=1` | ✅ | ❌ 缺失 | 256MB 下 17.7x QPS（[[DEC-070]]） |
| `PAGE_MERGE_BG=1` | ✅ | ❌ 缺失 | 连续页合并优化 |

**证据**：M=16 EF=100 1T 256MB，CON-SLA-020 基线 1,076 QPS，R5 实测 146 QPS，差 7.4x。
recall 一致（97.76% vs 96.00%），证明仅 I/O 优化缺失。

### 问题 2: 基线未对齐 DEC-086 最优参数

CON-SLA-020 (2026-08-06 promoted) 用 **EF=100 + BASE 模式** 测基线。
sustained-param-retuning (2026-08-07 promoted, DEC-086) 发现 **EF=90 + ADAPTIVE + eef=40** 更优：

| 配置 (256MB 16T) | 聚合 QPS | Recall | 来源 |
|------------------|---------|--------|------|
| EF=100 BASE (CON-SLA-020) | 2,078 | 96.00% | 旧基线 |
| EF=90 ADAPTIVE eef=40 (DEC-086) | 3,176 | 95.10% | 新最优 |

CON-SLA-020 的 trunk-ref (47ed9e7) 未更新为 c63694f，基线数字未用新参数重测。

pipeline-param-retuning POC 的 baseline 应以 **DEC-086 最优配置** 为对照，
而非 CON-SLA-020 的旧 BASE 基线。

### 根因

1. `run_p1.sh` / `run_strict.sh` 从早期脚本继承 env 配置，未对照 CON-SLA-020 校验
2. CON-SLA-020 在 R5 前一天 promote，R5 脚本未及时对齐
3. sustained-param-retuning promote (DEC-086) 只改了 API 推荐值注释，未更新 CON-SLA-020 基线
4. POC 的 baseline_trunk_sha=c63694f 但实际未使用 DEC-086 的最优参数作为对照

## 修正方案

### 1. 废弃旧数据
- R0–R5 全部 QPS 数据废弃（recall 数据有效，不受 I/O 优化影响）
- evidence 文件标注 deprecated

### 2. 修正测试脚本
添加 `L4_WILLNEED=1 PAGE_MERGE_BG=1`，对齐 CON-SLA-020 env 配置。

### 3. 双基线对照
每个实验同时报告两组基线对比：

| 基线 | 配置 | 用途 |
|------|------|------|
| **BASE 基线** | M=16, EF=100, ADAPTIVE_EF=0 | 对齐 CON-SLA-020，隔离 M_graph 效果 |
| **ADAPTIVE 基线** | M=16, EF=90, ADAPTIVE_EF=1, eef=40 | 对齐 DEC-086 最优，反映生产配置 |

实验配置本身仍用 BASE 模式（ADAPTIVE_EF=0）扫描 M_graph × EF，
以隔离 M_graph 的影响。但最终 R5' 复验时加测 ADAPTIVE 模式。

### 4. 修正后标准配置

**BASE 模式（扫描用）**:
```bash
export CACHE_MB=64
export TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
export L4_WILLNEED=1          # ← 新增
export PAGE_MERGE_BG=1         # ← 新增
export WILLNEED_BG=1
export VL_POOL_THREADS=14
export FLAT_VEC_MB=64          # 256MB cgroup
export ADAPTIVE_EF=0
```

**ADAPTIVE 模式（复验用，对齐 DEC-086）**:
```bash
# 同上，但：
export REFINE_EF=90
export ADAPTIVE_EF=1
export ADAPTIVE_EASY_EF=40
```

### 5. CON-SLA-020 trunk-ref 更新（另案）
CON-SLA-020 的 trunk-ref 应从 47ed9e7 更新为 c63694f（含 DEC-086 推荐值）。
基线数字是否需要用新参数重测，由后续 promote 提案决定，不在本 POC 范围内。

## 验收标准

1. BASE 基线 M=16 EF=100 1T 256MB 聚合 QPS MUST 对齐 CON-SLA-020（≥ 950）
2. ADAPTIVE 基线 M=16 EF=90 1T 256MB 聚合 QPS SHOULD 对齐 DEC-086 范围
3. 所有实验 MUST 在 [[CON-SLA-014]] 严格 cgroup 隔离下执行
4. 所有实验 MUST 遵守 [[CON-SLA-019]] 禁预热
5. Recall 数据可从旧实验继承

## 实验计划（重跑）

| 阶段 | 内容 | 模式 | 预计时间 |
|------|------|------|---------|
| R0' | M_graph={16,24,32,48} × EF={60,80,100,120} 1T | BASE | ~30 min |
| R1' | GBDT/ADAPTIVE (M=24 EF=60) 1T | ADAPTIVE | ~10 min |
| R2' | PQ M={16,32,64} scan (M=24 EF=60) 1T | BASE | ~15 min |
| R3' | M={16,24} × EF={60,80} × T={4,8,16} | BASE | ~30 min |
| R4' | Block size={32K,64K,128K} (M=24 EF=60) 1T | BASE | ~15 min |
| R5' | 完整 strict 256MB 复验 + ADAPTIVE 基线对比 | BASE+ADAPTIVE | ~45 min |

## 影响范围

- 仅 `poc/pipeline-param-retuning/`：脚本修正 + evidence 更新
- **不改 Trunk `src/`**（[[BEH-018]] 第 6 条）
- **不改 stable 条款**（[[CON-POC-001]]）
- CON-SLA-020 trunk-ref 更新另案处理
