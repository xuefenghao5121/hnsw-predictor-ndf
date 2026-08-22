# Proposal: POC — 多 Top-K 召回口径对齐 (Recall@1/@10/@100)

> track: poc
> Status: Pending confirmation
> 日期: 2026-08-18
> Trunk SHA: a143392
> origin: human_intent
> 关联: [[CHR-006]], [[CON-HONEST-002]], [[CON-SLA-014]], [[CON-SLA-019]], [[CON-SLA-020]], [[DEC-084]]

## 0. 意图原文 (origin: human_intent)

> 我们能不能增大Top-K的值来进行测试，看看结果是不是更有利于我们？
> 因为业界DiskANN等论文好像在测试的时候设置了较大的Top-K，来获得相对更好结果。

## 1. 结论先行

增大 Top-K **确实会让 Recall 数字单调变大**（数学上 Recall@k 对 k 单调不减），
但这是一把双刃剑：**换大 K 抬高头条数字属于 benchmark 挑选（cherry-picking），
与本仓库 [[DEC-084]] / [[CON-HONEST-002]] 确立的诚实测量纪律直接冲突**。

且**事实前提需要纠正**：DiskANN 用的是**更小**的 K，不是更大：

| 来源 | 召回口径 | 相对本仓 Recall@10 |
|------|---------|-------------------|
| DiskANN (NeurIPS'19) | `1-recall@1` / `5-recall@5` | **更严格**（K 更小） |
| big-ann-benchmarks (NeurIPS'21) | `recall@10` | 相同 |
| ann-benchmarks | `k=10`（默认） | 相同 |

本提案定位：**把「多 K 召回口径」做成一个诚实的观测/对齐面（POC），
而非修改 [[CHR-006]] 的 Recall@10 ≥ 95% must 门槛**。

## 2. 背景与现状

### 2.1 本仓当前口径

- [[CHR-006]] Must 门槛：**Recall@10 ≥ 95%**（SIFT1M, 512MB cgroup, [[CON-SLA-014]]）。
- [[CON-SLA-011]] O_DIRECT 地板同样锚定 Recall@10。
- 代码层 K 已是可调参数：`benchmark_diskhnsw.cpp`（`k = argv[8]`）、
  `benchmark_sustained.cpp`、`test_disk_hnsw.cpp`（`[k=10]`）、
  `scripts/hdf5_to_fvecs.py`（`--k`，GT top-K 默认 10）。
- 即：**换 K 在 harness 层面几乎零改动**，GT 只需按 K 重新导出/扩展。

### 2.2 数学事实：Recall@k 对 k 单调不减

Recall@k = 近似 top-k 结果 ∩ 精确 top-k / k。k 越大，「命中某个真近邻」的门槛越
宽松，Recall 值只升不降。因此**任何系统**把口径从 @10 换到 @100，Recall 都必然
看起来更好——这**不构成任何算法改进**，纯粹是度量口径变化。

## 3. 业界口径调研（web 检索，非训练记忆）

1. **DiskANN**（Subramanya et al., NeurIPS 2019）：报告 `1-recall@1`（DEEP1B/SIFT1B，
   "95%+ 1-recall@1 @ 16 cores"）与 `5-recall@5`（ANN_SIFT1M）——K 均**小于等于 10**，
   属**更严**口径，与「DiskANN 用大 Top-K」的直觉相反。
   - 来源：https://proceedings.neurips.cc/paper_files/paper/2019/hash/09853c7fb1d3f8ee67a61b6bf4a7f8e6-Abstract.html
   - 来源：https://suhasjs.github.io/files/diskann_neurips19.pdf
2. **big-ann-benchmarks**（NeurIPS'21 Competition Track）：官方 metric 明确为
   **`recall@10`**（T1/T2 分别测固定 QPS 下的 recall@10）。
   - 来源：https://big-ann-benchmarks.com/neurips21.html
3. **ann-benchmarks**（Bernhardsson）：默认每数据集标注 `k=10`，Recall 为真近邻命中
   比例。
   - 来源：https://ann-benchmarks.com/index.html
4. **Recall@1 vs Recall@100 语义差异**（Zilliz/Milvus 参考）：Recall@1 衡量「首位排序
   质量」，Recall@100 衡量「相关项是否落在更大候选集某处」——两者回答不同问题，
   不可互相替代，也不可混用口径比较。
   - 来源：https://zilliz.com/ai-faq/in-evaluating-vector-search-what-are-the-differences-between-recall1-vs-recall100-or-precision1-vs-precision10-and-what-do-those-differences-reveal-about-a-systems-behavior
   - 来源：https://arxiv.org/html/2606.04522v1（"ANN Search: Recall What Matters"，
     讨论 Recall@k 作为调优/评估主指标的问题）

> ⚠️ 上述均为**公开文献/标准口径**，非本仓实测；**不构成新 SLA，也不得写成
> must 契约**，仅作对齐参考。

## 4. 分析：合法 vs 不合法的两种动机

| 动机 | 做法 | 判定 |
|------|------|------|
| 换大 K 抬高头条 Recall | 把 must 门槛从 @10 改 @100 再宣称「更好」 | ❌ 违反 [[CON-HONEST-002]]，等同 warmup 造假 |
| **多 K 并行报告，对齐业界可比口径** | 同一次 sustained 测 @1/@10/@100，分栏输出 | ✅ 合法，增强可比性与诚实度 |

本提案采纳第二种。**must 门槛 Recall@10 保持不变**；新增 @1/@100 仅作为
「口径对齐 / 与 DiskANN 等跨论文可比」的附加观测，不作为验收通过条件。

## 5. 提议的 POC 方向

`poc/topk-recall-alignment/`（新建，track=poc）：

- **R0 口径扩展**：在现有 `benchmark_sustained` 上增加多 K 召回输出
  （Recall@1 / @10 / @100），GT 按 K 扩展（复用官方 10K query + 官方 GT，
  扩 GT 到 K=100 或改用全量精确近邻导出）。
- **R1 对齐对照**：SIFT1M 512MB / 256MB × 1/4/16T，输出三栏 Recall，观察
  @1→@10→@100 的提升曲线，量化「口径放宽带来的账面增益」。
- **R2 跨论文对齐表**：把 DiskHNSW 的 @1/@10/@100 与 DiskANN 报告口径
  （@1/@5）、big-ann-benchmarks（@10）并排，评估诚实可比位置。

**验收与护栏（写入 POC 的 TOPIC/DESIGN，不写 Trunk 条款）：**
- MUST NOT 修改 [[CHR-006]] Recall@10 ≥ 95% 的 must 门槛。
- MUST 在每次多 K 报告中显式标注「口径 K」，禁止用 @100 数字替换 @10 数字。
- MUST 沿用 [[CON-SLA-019]] 禁预热 + [[CON-SLA-020]] sustained 基线 + [[CON-SLA-014]]
  严格隔离，避免重蹈 [[DEC-084]] 的 harness 造假覆辙。

## 6. 非目标 / 约束

- 不落地任何 Trunk 条款（不新增 DEC/SLA/must，不写 spec/meta 正文）。
- 不改 [[CHR-006]]、[[CON-SLA-011]] 的 Recall@10 门槛。
- 不把「@100 更高」当作性能优化成果写进 CHR/DEC 收益声明。
- 本提案仅为 POC 探索，停在「已确认」人工回执，不 approve、不 forge approved_by。

## 7. 参考资料

- DiskANN 摘要：https://proceedings.neurips.cc/paper_files/paper/2019/hash/09853c7fb1d3f8ee67a61b6bf4a7f8e6-Abstract.html
- DiskANN PDF：https://suhasjs.github.io/files/diskann_neurips19.pdf
- big-ann-benchmarks 规则：https://big-ann-benchmarks.com/neurips21.html
- ann-benchmarks：https://ann-benchmarks.com/index.html
- Recall@1 vs @100：https://zilliz.com/ai-faq/in-evaluating-vector-search-what-are-the-differences-between-recall1-vs-recall100-or-precision1-vs-precision10-and-what-do-those-differences-reveal-about-a-systems-behavior
- arXiv 2606.04522 "ANN Search: Recall What Matters"：https://arxiv.org/html/2606.04522v1

---

提案已生成：`spec/open/proposal-poc-topk-recall-alignment.md`。请审阅，确认后回复「已确认」。
