# DEC-100: page-packer 负结果 — 页内贪心打包边际不足 {#DEC-100}

> date: 2026-08-18
> affects: BEH-037, DEC-018
> Rejects: page-packer

## Context

vecblock-cluster-reorder（[[BEH-037]]）已 promote within-block cluster sort。
page-packer 假设：cluster 段内用 graph adjacency 贪心页打包，可提高页命中率与 QPS。

依赖：vecblock-cluster-reorder (promoted)；探索面：`spec/20-behavior/vecblock-layout`。

Human 判定（2026-08-18，原文）：负结果关闭：本方向已无继续价值，走 reject（不改 Trunk src/）。

## 实验

R0（2026-08-10，cluster sort vs cluster + page packing）：

| | QPS | steady | recall |
|--|:---:|:---:|:---:|
| A: cluster only | 1,744 | 2,045 | 96.60% |
| B: cluster + pack | 1,769 | 2,065 | 96.60% |
| Δ | **+1.4%** | +1.0% | 0 |

分析：`shuffle_vecblocks` 对 cluster-sorted blocks 仅 ~2.3 vectors/cluster/block
可供重排，优化空间有限；page packing 不是方向 B 的主要收益来源。

## 根因

页内贪心打包相对已有 cluster sort 的边际收益约 +1.4%，不足以支撑继续探索或合入 Trunk。
方向已无继续价值。

## 结论

- **不 promote 任何条款** — 无 topic-owned draft；[[BEH-037]] / DEC-018 维持现状
- **不改 Trunk `src/` / `include/` / `tests/`** — 实现从未合入（`trunk_src_writes=none`）
- 负结果闭环：TOPIC=`rejected`，binder archive，`Rejects: page-packer`

若再探索页内打包假设：MUST 开平级新 topic + `depends_on_topics: page-packer`
（[[BEH-025]] 关闭后重启），MUST NOT 将本 topic 改回 exploring。

> source: poc/page-packer/ndf/TOPIC.md ; poc/page-packer/NOTES.md ; spec/open/proposal-reject-page-packer.md
> track: reject ; Topic: page-packer
> Rejects: page-packer
