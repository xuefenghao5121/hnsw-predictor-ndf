# hierarchical-vamana-build — L3 语义核（行为预言机）

> model: hierarchical-vamana-build
> 引用条款: [[BEH-027]]、[[ARCH-007]]
> track: promote ; Topic: hierarchical-vamana
> source: poc/hierarchical-vamana/ndf/TOPIC.md ; spec/open/proposal-promote-hierarchical-vamana.md @ d0ae5dd

本文件为 NDF L3 语义核（[[META-004]]）：只承载启用条件、时机、操作与不变量。
MUST NOT 迁入 poc 树 / git patch 账本 / COMMITS 行 / 性能证据数字（[[CON-POC-001]]）。

## 启用 / 何时使用

- **build-time**（索引构建期）替换 Trunk 默认整图 hnswlib 建边；**默认开启**（[[DEC-003]]）。
- 搜索路径 / Fine Rerank / BlockCache / PQ 不变；不晋升 GBDT（`LEARNED_EF`）。
- 非 search-time 行为；本语义核不约束查询期路径。

## 时机（timing）

- 发生在 `build_index` 建图阶段，先于 `bfs_reorder` / `write_blocks` / PQ / 查询。
- 建图可多线程（OpenMP）；索引写完后才开启 sustained 查询线程池（与 Trunk 同）。

## 操作 / 参数

| 参数 | 默认 | 语义 |
|------|------|------|
| `HV_M` | 16 | HNSW 层分配基准 M（mL = 1/ln M） |
| `HV_R0` | 32 | L0 层 RobustPrune 候选出度上限 R |
| `HV_RUP` | 16 | 上层（L≥1）RobustPrune 候选出度上限 R |
| `HV_BEAM` | 32 | 建图 beam（GreedySearch/construction） |
| `HV_ALPHA` | 1.2 | RobustPrune α |
| `HV_ALPHA2` | 0 | 二遍 α（0=关闭） |
| `HV_ROUNDS` | 3 | 建图迭代轮数 |
| `HV_SEED` | 42 | 随机种子 |

层分配：`level = floor(-ln(U) * mL)`，`U ~ Uniform(0,1)`。
每层建图：随机初始化 → 迭代（beam/GreedySearch 生成候选 → RobustPrune(α) 剪枝）→
对称化 → 二遍 prune。
导出：`GraphStructure`（与原 `extract_graph` 输出同格式），复用现有 DiskHNSW 后段流水线。

## 不变量（invariants）

1. 层分配与边端点层关系一致：无指向更高层的非法边。
2. prune 语义：α 越大 → 剪枝越弱 → 边越多（本实现相反于标准 DiskANN 直觉）。
3. 导出 L0 邻接必须可被现有 DiskHNSW 搜索路径加载（或文档化不兼容点）。
4. 搜索召回与全内存对照可比（目标 ≥95%，[[VER-006]]）。
