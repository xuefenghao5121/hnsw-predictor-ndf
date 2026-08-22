# Proposal: 负结果闭环 — page-packer rejected {#PROP-REJECT-PAGE-PACKER}

> track: poc
> Status: Implemented on 2026-08-18
> Confirmed: 已确认
> reviewed: 已审核
> 日期: 2026-08-18
> Subject: page-packer topic 负结果关闭
> 对齐: [[BEH-020]]
> Rejects: page-packer
> 关联: [[BEH-037]], DEC-018
> trunk_src_writes: none

## 1. 根因

Human 判定（2026-08-18，原文）：负结果关闭：本方向已无继续价值，走 reject（不改 Trunk src/）。

Human 判定（2026-08-17）：`page-packer` 为历史 exploring POC，R0 对 cluster-only
边际约 +1.4%，已无继续探索/合入价值，直接负结果关闭。

**R0 证据**（NOTES，2026-08-10，cluster sort vs cluster + page packing）：

| | QPS | steady | recall |
|--|:---:|:---:|:---:|
| A: cluster only | 1,744 | 2,045 | 96.60% |
| B: cluster + pack | 1,769 | 2,065 | 96.60% |
| Δ | **+1.4%** | +1.0% | 0 |

分析（NOTES）：shuffle_vecblocks 对 cluster-sorted blocks 仅 ~2.3 vectors/cluster/block
可供重排，优化空间有限；page packing 不是方向 B 的主要收益来源。

> source: poc/page-packer/NOTES.md ; poc/page-packer/ndf/TOPIC.md
> track: reject ; Topic: page-packer

## 2. 废弃 ID 列表

| ID | 位置 | 当前 status | 动作 |
|----|------|------------|------|
| — | — | — | **无** — 本主题未写入 Trunk draft/stable 条款 |

## 3. 提案状态变更

| 提案 | 动作 |
|------|------|
| _(none)_ | N/A — 无关联 open 产品提案需 Rejected |

## 4. Trunk 确认

page-packer 实现仅在 `poc/page-packer/`（含 `run_r0.sh` 等），从未合入 `src/` /
`include/` / `tests/`。`trunk_src_writes=none`；无需 revert Trunk。

## 5. 归档

- 提案「已确认」并落地后：`poc/page-packer/ndf/` 迁入 `spec/archive/2026-08/poc-page-packer/`
- `poc/page-packer/` 代码可保留（复现参考）
- TOPIC / NOTES 头 status → `rejected`；DEC 含 `Rejects: page-packer`

## 6. 后续影响

- page-packer topic 关闭（负结果）；[[BEH-037]] cluster vecblock 保持现状
- 若再探索页内打包假设：MUST 开平级新 topic + `depends_on_topics: page-packer`，
  MUST NOT 将本 topic 改回 exploring

## 7. 非目标

- 不删除 POC 代码树（除装订器归档迁移）
- 不改写已推送历史
- 不改 Trunk `src/` 或 stable 条款
- 不把 NOTES 散文当成已选 `selected_decision`（落地时显式写 TOPIC header）

---

Status: Implemented on 2026-08-18；Confirmed: 已确认；reviewed: 已审核。
Close-apply：DEC-100 / TOPIC=rejected / binder archive；integrate N/A（`trunk_src_writes=none`）。
