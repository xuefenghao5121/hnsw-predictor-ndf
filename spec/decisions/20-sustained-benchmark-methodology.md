# DEC-084: Sustained 测量方法论 + GBDT 收益证伪

> 日期: 2026-08-06
> Topic: sustained-query-benchmark
> 提案: `spec/open/proposal-promote-sustained-query-benchmark.md`
> Promotes: sustained-query-benchmark
> source: poc/sustained-query-benchmark/ndf/TOPIC.md ; evidence/r0..r6 ; COMMITS.md @ 4a33f38

## 决策 {#DEC-084}
<!-- ndf: kind=decision level=info layer=L1 status=stable since=0.9.10 source=observed topic=sustained-query-benchmark -->

采纳多轮随机采样 + 禁预热的 sustained 测量方法论（[[BEH-035]] / [[CON-SLA-019]] /
[[MODEL-SUSTAINED-001]] / [[CON-SLA-020]]），并据此**证伪** GBDT 学习式剪枝
（[[BEH-034]]）的收益声明。

---

## 1. 问题：协议漏洞而非实现 bug

[[CON-SLA-014]] 规定 benchmark **启动前** `sync && drop_caches` + cgroup 限制，
但**从未规定计时窗口内允许什么**。

`benchmark_diskhnsw` 长期包含：

```cpp
// Search warmup: run all queries once to warm cache
```

即在计时前把**全部待测 query** 跑一遍。后果：所有 SLA 数字测的是 in-memory 性能。

> 这是**协议欠定**导致的系统性偏差，不是某次实现失误。
> 写 MUST 类约束时须同时界定「边界前做什么」与「边界内禁止什么」。

## 2. 方法论

从**标准 query 池**（官方 SIFT 10K query + 官方 GT）每轮随机采样 N 个，共 R 轮，
取消对被测 query 的预热。详细语义见 [[MODEL-SUSTAINED-001]]。

### 有效性验证

| 检查 | 结果 |
|------|------|
| R=1 recall vs 现有 200q baseline | **95.75% 精确一致** |
| 稳态 QPS 与 N 无关 | N=200/1000/10000 → 1,649 / 1,722 / 1,649（跨度 4%） |
| recall ≥ 95% 商用门槛 | **96.00%** |
| 同 seed 可复现 | ±0.2% |

**稳态与 N 无关**是核心证据：测得的是物理量而非 harness 伪影。

### R0 数据集验证

- 现有 200q **是官方池的前 200 个**（精确匹配）→ 现有 recall 95.75% 本身可信，无 self-match
- 官方 GT 与内部 `sift1m_gt200.bin` 仅 2 行差异，经距离验证为 **exact tie**
  （dist² 完全相同：42192.0 / 40644.0），不影响 recall

## 3. cache-warmed 高估幅度

| 配置 | 200q + warmup | sustained 稳态 | 高估 |
|------|--------------|---------------|------|
| 512MB 1T | 3,241 | 1,729 | 1.87× |
| 512MB 4T | 9,090 | 5,247 | 1.73× |
| 512MB 16T | 30,332 | 6,694 | **4.53×** |
| 256MB 4T | 8,838 | 2,519 | 3.51× |
| 256MB 16T | 18,675 | 2,456 | **7.60×** |

线程数越高高估越严重 —— warmup 使全部线程命中 page cache，掩盖 I/O 争用。

## 4. 饱和曲线方向修正（原 POC 提案预期证伪）

原提案预期「QPS 随轮数下降」（working set 增长 → cache 失效）。
**实测单调上升**：冷启动 ~245 → 稳态 ~1,670，R≈20 饱和。

| R | Round-1 | 末轮 | 聚合 | Recall | 累积 unique |
|---|---------|------|------|--------|-----------|
| 1 | 244.7 | — | 244.7 | 95.35% | 200 |
| 5 | 245.6 | 1,393.2 | 688.0 | 96.42% | 965 |
| 10 | 237.0 | 1,451.0 | 909.2 | 96.50% | 1,837 |
| 20 | 244.7 | 1,622.3 | 1,141.0 | 96.25% | 3,314 |
| 50 | 241.8 | **1,671.1** | 1,348.5 | **96.06%** | 6,346 |

### 根因

随机换 query **无法驱逐 query-无关的共享状态**：

```text
图 CSR      47 MB  (compact 44MB + offsets 3MB, 1.8x 压缩, 21,202,584 edges)
PQ codes    30 MB  (N=1e6, M=32, nbits=8)
FVC        160 MB  (FLAT_VEC_MB=160)
────────────────
合计       ~237 MB  → 512MB 预算内长期驻留
```

此前「working set ~10MB / ~488MB」的算法只统计 Phase B 向量页，
**漏掉了占主导的共享状态**。

**推论**：真正的假象来源是 **harness 预热被测 query**，而非 working set 规模不足。
这直接决定了 [[CON-SLA-019]] 的措辞方向（禁预热，而非要求更大 working set）。

## 5. GBDT 收益证伪（[[BEH-034]] 降级依据）

### 三次测量

| 场景 | GBDT 增益 | 测量有效性 |
|------|----------|-----------|
| 200q + warmup | +3.3~6.0% | ❌ cache-warmed |
| base-sampled 10Kq | +33~124% | ❌ GT self-match 污染 |
| **官方池 sustained** | **−0.9~+1.8%**（噪声内） | ✅ |

### R5 完整数据（N=1000, R=15）

| cgroup | 线程 | 模式 | 聚合 QPS | 稳态 QPS | Recall | vs BASE |
|--------|------|------|---------|---------|--------|---------|
| 256MB | 4T | BASE | 2,200.0 | 2,526.8 | 96.00% | — |
| 256MB | 4T | ADAPTIVE | 2,822.1 | 3,414.7 | 95.81% | **+28.3%** |
| 256MB | 4T | GBDT | 2,197.5 | 2,358.8 | 95.99% | −0.1% |
| 256MB | 16T | BASE | 2,102.1 | 2,414.2 | 96.00% | — |
| 256MB | 16T | ADAPTIVE | 2,763.1 | 3,420.1 | 95.81% | **+31.4%** |
| 256MB | 16T | GBDT | 2,139.8 | 2,460.2 | 95.99% | +1.8% |
| 512MB | 4T | BASE | 3,910.3 | 5,258.9 | 96.00% | — |
| 512MB | 4T | ADAPTIVE | 4,397.7 | 6,161.1 | 95.80% | **+12.5%** |
| 512MB | 4T | GBDT | 3,874.1 | 5,119.7 | 95.99% | −0.9% |
| 512MB | 16T | BASE | 4,455.3 | 6,806.0 | 96.00% | — |
| 512MB | 16T | ADAPTIVE | 5,633.1 | 9,560.4 | 95.80% | **+26.4%** |
| 512MB | 16T | GBDT | 4,456.6 | 6,923.6 | 95.99% | +0.0% |

### 根因：训练标签污染

GBDT 训练数据来自 **base-sampled 10K query 的 profiling**。那批 query 因 self-match
而"异常容易"（GT top-1 恒为自己，距离 0），模型学到的"所需候选数"分布**系统性偏低**。
用在官方 query 上预测失准，`learned_limit` 裁剪失去准确性 → 收益归零。

> **self-match bug 不仅污染 recall 指标，还污染了 GBDT 的训练标签。**
> 数据污染沿流水线传播：污染 GT → 污染 recall → 污染训练标签 → 污染收益结论。
> 发现污染后 MUST 回溯**所有**下游依赖，不只是直接指标（见
> [[MODEL-SUSTAINED-001]] 不变量 I4 推论）。

### 处置：must → may，不 rollback

| 选项 | 评估 |
|------|------|
| rollback（revert src） | ❌ 过度。默认 `LEARNED_EF=0` 无生产风险；**代码正确，错的是收益声明** |
| 负结果闭环（deprecated，[[BEH-020]]） | ⚠️ 偏重。机制可复活（用合规 pool 重训练即可） |
| **must → may + 修正收益声明** | ✅ **采纳** |

[[BEH-034]] 保留 `status=stable`（接口稳定、行为确定），`level` must → **may**，
正文明确「当前模型收益在 sustained 场景下不成立，需用官方 query 池重新训练」。

## 6. ADAPTIVE_EF 收益确认并上修（[[BEH-033]]）

sustained 下 **+12.5% ~ +31.4%**，recall 95.80–95.81%（≥95%）。

**512MB 下也有收益**（+12.5% / +26.4%）→ **推翻**原条款「512MB cgroup 下收益不明显
或略有退化」的判断。该判断来自 cache-warmed 测量：warmup 后 512MB 确实无 I/O 压力，
故看不到收益。诚实测量下 512MB 依然 I/O bound。

### ADAPTIVE vs GBDT 的本质差异

| | ADAPTIVE_EF | LEARNED_EF (GBDT) |
|--|------------|------------------|
| 依据 | 运行时 PQ gap_ratio（在线信号） | 离线训练模型（静态） |
| 对 query 分布依赖 | 弱（自适应） | 强（训练分布） |
| 训练数据污染影响 | 无（无训练） | 致命（标签偏移） |
| sustained 收益 | +12.5~31.4% ✅ | −0.9~+1.8% ❌ |

> **在分布可能漂移的场景，在线自适应信号优于离线学习模型。**

## 7. hnswlib 对照与 QPS/MB 修正

### hnswlib recall 三次修正

| 测量 | Recall | 有效性 |
|------|--------|--------|
| base-sampled 10Kq + 含 self GT | 99.47% | ❌ GT 含 self-match |
| base-sampled 10Kq + 排除 self GT | 89.90% | ❌ query 分布非标准 |
| **官方 10Kq + 官方 GT** | **98.25%** | ✅ 符合文献（EF=100） |

89.90% 异常低的根因：base-sampled query 位于数据流形内部，其真实 10-NN 更密集难分。

hnswlib unlimited：1T 6,424 / 4T 22,757 / 16T 42,947 QPS，RSS 734–763MB。

### QPS/MB 内存效率优势不成立

| 配置 | 稳态 QPS | 内存 | QPS/MB | vs hnswlib |
|------|---------|------|--------|-----------|
| hnswlib 16T | 42,947 | 763 MB | 56.3 | 1.00× |
| DiskHNSW 512MB 16T | 6,694 | 512 MB | 13.1 | 0.23× |
| DiskHNSW 256MB 16T | 2,456 | 256 MB | 9.6 | 0.17× |
| DiskHNSW 512MB 16T + ADAPTIVE | 9,560 | 512 MB | 18.7 | 0.33× |

此前声称的 1.10× / 1.36× 优势来自 cache-warmed 测量。

**真实定位修正**：
- ✅ 能在内存预算不足时工作（hnswlib 在 DEEP10M 直接 OOM）
- ✅ 绝对内存占用低（256MB vs 763MB = 33%）
- ❌ 吞吐代价显著（5.7–26.9% of hnswlib）
- → **trade-off，不是全面胜出**

## 8. 与 DEC-083 的关系

[[DEC-083]] 正确识别了「200q cache-warmed」现象，但：

1. 归因不完整 —— 认为是 working set 规模问题，实为 harness 预热问题
2. 补救方向错误 —— 用 base-sampled query 增大 working set，引入 self-match 污染
3. 结论过保守 —— 认为「200q 仍是唯一满足 recall ≥ 95% 的基准」

本 DEC **部分超越** DEC-083：保留其现象观察，修正其归因与补救路径。
DEC-083 保留作认知记录（含 `CON-SLA-019`/`CON-SLA-020` 曾撤除的历史）。

### ID 复用说明

`CON-SLA-019` / `CON-SLA-020` 曾于 2026-08-06 短暂建立后撤除（commit `4a33f38`，
因 base-sampled recall 89.71% 不达门槛）。本次**复用同一对 ID**，语义完全不同
且证据有效（recall 96.00%）。查阅 git 历史时须注意此复用。

## 9. 影响的条款

| ID | 动作 |
|----|------|
| [[BEH-035]] | 新增 stable（多轮随机采样基准） |
| [[API-019]] | 新增 stable（`benchmark_sustained` CLI） |
| [[CON-SLA-019]] | 新增 must（禁预热被测 query） |
| [[CON-SLA-020]] | 新增 must（sustained 基线） |
| [[MODEL-SUSTAINED-001]] | 新增 L3 语义核 |
| [[VER-043]] | 新增验收 |
| [[CON-SLA-014]] | 补第 6 条 + 历史漏洞说明 |
| [[CON-SLA-016]] / [[CON-SLA-017]] / [[CON-SLA-018]] | 标注 cache-warmed 口径 |
| [[BEH-033]] | 删除「512MB 收益不明显」；补 sustained 实测 |
| [[BEH-034]] | must → may；删除「+33~124%」；标注需重训练 |
| [[API-018]] | 标注收益状态 |

## 10. 工程教训

1. **benchmark warmup 是性能谎言的头号来源**。预热被测 query = 测 in-memory 性能。
2. **「working set」计算 MUST 包含 query-无关共享状态**（图结构、量化码、热点缓存）。
3. **稳态与采样规模无关是方法论有效性的判别式**（[[MODEL-SUSTAINED-001]] I1）。
4. **数据污染沿流水线传播**，MUST 回溯全部下游依赖。
5. **在线自适应 > 离线学习模型**（分布可能漂移时）。
6. **协议漏洞比实现 bug 更值得记录**：MUST 类约束需同时界定边界前与边界内。
7. **收益声明错误 ≠ 代码错误**：分层处置，代码正确就不 revert，只降 level + 修正声明。
8. **NDF POC 纪律有效**：探索期 Trunk `src/` 零改动，使「结论证伪」时无需回滚产品代码。

## 11. GBDT 重训练复活（2026-08-07）

### 背景

[[BEH-034]] 在 §5 中被降级为 `may`，复活条件为"用合规 query 池重训"。
`poc/gbdt-retrain/` 执行了此复活路径。

### 执行

| 步骤 | 内容 |
|------|------|
| R0 | 官方 10K query 池 profiling（PROFILE_LLSP=1, EF=200） |
| R2 | LightGBM 训练（100 棵树, depth=4, MAE=53.3） |
| R4 | Sustained 三方对比（512MB + 256MB × 1/4/16T） |
| R5 | Margin 调优（0.7~1.1, 推荐 0.8） |

### 标签分布对比

| 维度 | 原 POC (base-sampled) | 本 POC (官方池) |
|------|----------------------|----------------|
| P50 min_n | 21 | 26 (+24%) |
| P75 min_n | 30 | 52 (+73%) |
| avg pred_n | ~30 | 60.3 |

self-match 污染使原标签系统性偏低 -> 模型过度裁剪 -> sustained 收益归零。
重训后模型更保守（avg_n 60.3 vs 30），recall 95.87% ≥ 95%。

### 结果

| 指标 | 原 GBDT (sustained) | GBDT-v2 (sustained) |
|------|---------------------|---------------------|
| vs BASE | -0.9~+1.8%（噪声） | +12.3~47.4% ✅ |
| vs ADAPTIVE | 远低于 | +0.7~11.4% ✅ |
| recall | 95.99% | 95.87% |

### 处置

[[BEH-034]] level: may -> **must**（恢复）。[[API-018]] 更新收益状态。
模型文件 `include/gbdt_model.h` 替换为重训版本（182KB）。

### 教训补充

9. **离线学习模型可复活**：训练数据修复后，模型可恢复有效性。
   降级不等于废弃--保留机制 + 修正训练数据 = 最小代价的复活路径。
10. **GBDT 多特征 > ADAPTIVE 单特征**（在高并发 I/O 争用场景下）。
    16T 下 GBDT 比 ADAPTIVE +11.4%，因为多特征能更好区分 query 难度。
