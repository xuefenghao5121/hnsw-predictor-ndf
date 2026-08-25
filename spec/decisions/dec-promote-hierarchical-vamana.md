# DEC-003: 分层 Vamana 默认建图（promote hierarchical-vamana） {#DEC-003}
<!-- ndf: kind=decision level=must layer=L0 status=stable since=0.2 source=promote -->

**Context.** POC `hierarchical-vamana`（R0–R3）证得 H0 成立：分层 Vamana 建图在 sustained
口径下达对照召回（≥95%）并以更少无效边改善 QPS（代价 delta-varint 压缩变差、RSS 略增，
仍在 512MB cgroup 预算内）。promote 提案获「已审核」后进入落地。

**Decision.** 将 Trunk 默认建图由整图 hnswlib 替换为「HNSW 几何层分配 + 每层 Vamana
RobustPrune」，**默认开启**（非 opt-in），锁定运行点
`M=16 R0=32 Rup=16 beam=32 α=1.2 rounds=3 seed=42`（beam=32 为人类 override R2 agent
选 beam=64）。`extract_graph` 步骤并入 `build_index`；搜索路径 / PQ / BlockCache /
Fine Rerank 不变。

**Alternatives rejected.** opt-in 标志位（增加运行时分叉与双路径维护成本，H0 已证得收益）；
晋升 GBDT / `LEARNED_EF`（R0–R3 全程关闭，非本主题范围）。

**Source.** poc/hierarchical-vamana/ndf/TOPIC.md ; spec/open/proposal-promote-hierarchical-vamana.md @ d0ae5dd
