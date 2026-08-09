> track: poc
> topic: fine-rerank-incremental
> status: proposal
> 日期: 2026-08-09

# 提案: Fine Rerank 增量流水线 — 分批读取 + 早终止

## 背景

当前 Fine Rerank Phase B 采用**全量批量读取**架构：

```
collect 65 candidates → check cache → submit WILLNEED(all pages) → pread(all pages) → compute all L2
```

DEC-081 曾尝试早终止，但因「pread 架构下先批量读完全部页 → 再算距离，早终止只能省
几 ns 的 L2 计算，不能省已完成的 I/O」而 **rejected**。

**关键洞察**：如果改变读取模式，**分批增量读取** + 基于 PQ 距离的**批间早终止**，
就能在批之间省掉 I/O（而不只是省计算）。这与 DEC-081 的根本区别在于：
**DEC-081 先读后停（省计算不省 I/O），本提案边读边停（省 I/O）**。

## 依赖

- `depends_on_topics`: pipeline-param-retuning (promoted, DEC-087 提供 EF=65 基线)
- `baseline_protocol`: [[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]] (sustained 金标)
- `baseline_trunk_sha`: e06ef31 (当前 Trunk tip)
- `baseline_config`: M=16 EF=65, 256MB cgroup, 1T, sustained (N=1000 R=15 seed=42)

## 基线

**DEC-087 R0'-R4' redo 的 256MB 1T sustained 数据（CON-SLA-020 口径）:**

| 配置 | Agg QPS | Steady QPS | Recall |
|------|---------|-----------|--------|
| M=16 EF=65 BASE | 2,483 | ~2,900 | 95.52% |

> baseline_trunk_sha = `e06ef31`
> recall 余量 = 0.52pp（< 0.5pp 门槛附近，ADAPTIVE 无效——见 DEC-088 决策树步骤 4）

## 假设

1. 候选已按 PQ 距离升序排列（`coarse_sorted`）
2. 最接近 query 的候选（PQ 距离最小）大概率出现在精确 L2 top-K 中
3. 当前 EF=65 下约 30-40 个候选需要磁盘 I/O（~50% cache 命中率），每查询 ~25-35 个 4KB pread
4. pread 等待是 1T 瓶颈（~60-80% 查询时间）

## 机制设计

### 核心：分批增量 pread + 批间早终止

```
Phase B (改造后):

1. 将 cache-miss 候选按 PQ 距离升序排列（已是此顺序）
2. 分成 B 个一批（B=16 初始值）
3. For batch_i in batches:
   a. 对 batch_i 的候选页提交 WILLNEED
   b. 等待内核 readahead（WILLNEED_BG 延迟 ~0）
   c. pread batch_i 的页面
   d. 计算 L2 距离，更新 top-K
   e. 早终止检查:
      - 统计 batch_i 中进入 top-K 的数量 (hit_count)
      - 如果 hit_count == 0 且 batch_i 的最小 PQ 距离 > k-th 精确距离 × margin
        → 剩余候选不可能改善 top-K，终止
      - 或者: 连续 T 个候选（非批）未改善 top-K → 终止
4. 剩余候选（未读）直接跳过
```

### 辅助：WILLNEED 延迟重叠

当前 WILLNEED 在全部页面上提交，内核 readahead 与 pread 之间的延迟未被利用。
增量模式下：

- batch 1 提交 WILLNEED + pread
- batch 1 计算期间，内核可以 readahead batch 2 的页（如果预先提交了 WILLNEED）
- 方案：对**下一批**提前提交 WILLNEED（lookahead=1），重叠 readahead 与当前批的计算

### 环境变量

```
FINE_INCREMENTAL=0|1   # 1=启用增量模式
FINE_BATCH_SIZE=16     # 每批候选数
FINE_EARLY_STOP=0|1    # 1=启用批间早终止
FINE_STOP_MARGIN=1.0   # PQ dist > k-th exact dist × margin → 终止
FINE_STOP_STREAK=0     # 连续 N 个未改善 → 终止 (0=禁用)
FINE_LOOKAHEAD=1       # 预提交 WILLNEED 的批数
```

## 与 DEC-081 的根本区别

| | DEC-081（rejected） | 本提案 |
|--|-------------------|--------|
| 读取模式 | 全量批量 pread | 分批增量 pread |
| 早终止时机 | 读完全部后跳过计算 | 批之间跳过后续 I/O |
| 节省 | L2 计算（ns 级） | pread I/O（us 级） |
| 架构改动 | 无（只是加 if） | 改 Phase B 循环结构 |
| 风险 | 无 | 中（需验证不伤 recall） |

## 写入边界

- MUST NOT 修改 Trunk `src/`、`include/`、`tests/`
- 在 `poc/fine-rerank-incremental/` 下编译独立 benchmark
- 可只读链接 Trunk `src/core/*.cpp` 和 `include/`（不改 Trunk 文件）
- 改动仅在 POC 目录内的 `disk_hnsw_poc.cpp`（从 Trunk 复制 + 修改 Phase B）

## 实验计划

| 阶段 | 内容 | 变量 | 验收 |
|------|------|------|------|
| R0 | 基线验证（未改代码，用 Trunk benchmark_sustained） | 无 | agg QPS ≈ 2,483 ± 5% |
| R1 | 增量 pread（FINE_INCREMENTAL=1, 无早终止） | B={8,16,32} | QPS 变化 ±5% 内（验证不退化） |
| R2 | 批间早终止 | B=16, margin={1.0,1.2,1.5}, streak={5,10,20} | Pareto 前沿 |
| R3 | WILLNEED lookahead=1 | B=16, lookahead={0,1,2} | 最优组合 |
| R4 | 最优组合完整验证 | 256MB 1T sustained | recall ≥ 95%, QPS vs R0 |

## 预期

- **乐观**：如果 ~50% query 在第 1 批后终止（省一半 I/O），agg QPS +30-50%
- **保守**：SIFT1M PQ 距离分布无明显拐点（DEC-081 R4 结论），早终止命中率可能不高
- **底线**：增量 pread 本身不退化（R1 验证），lookahead 重叠提供小幅收益

> recall 余量 0.52pp 意味着早终止必须保守，否则容易跌破 95%。这是核心风险。

## 风险

1. **recall 风险**：EF=65 recall 仅 95.52%，余量 0.52pp。早终止太激进 → recall < 95%
2. **SIFT1M 无拐点**：DEC-081 发现 SIFT1M 候选 PQ 距离分布无明显"拐点"
3. **batch 开销**：多次小 pread 可能比一次大 pread 慢（syscall 开销）
4. **WILLNEED 延迟**：内核 readahead 需要时间，lookahead=1 可能不够

## 缓解

- R2 从保守 margin 开始（1.5 → 1.2 → 1.0），逐级试探 recall 边界
- 记录每个 query 的终止批次分布（直方图），分析是否有收益空间
- R3 验证 batch_size 对 syscall 开销的影响

> source: spec/decisions/17-fine-rerank-early-termination-reject.md (DEC-081) ; spec/decisions/24-tuning-framework.md (DEC-088 因果模型) ; src/core/disk_hnsw.cpp:1740-1960 (Phase B 实现)
> track: poc ; Topic: fine-rerank-incremental
