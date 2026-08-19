# Proposal: Trunk NDF 卫生收口 r2 — open 变薄与关闭后才回合 {#PROP-META-TRUNK-HYGIENE-R2}

> track: process  
> Status: Implemented on 2026-08-03  
> 日期: 2026-08-03  
> 关联: [[CHR-008]], [[BEH-018]], [[BEH-019]], [[BEH-020]], [[BEH-025]], [[CON-POC-001]], [[DEC-HYGIENE-001]], [[ADR-META-001]]  
> 场景: 规范卫生 / Trunk 收口

## 1. 动机

产品 `spec/open/` 堆积 Implemented/Rejected 与 validation 报告，与 `20–50` 中 draft
探索条款交织，读者误以为 Trunk SoT 在持续胀大。双轨要求：**先收口 Trunk，再在 POC
实验；主题关闭（promote/reject）时才做产品 NDF 与 `src/` 回合**。

## 2. 决策

### 2.1 `spec/open/` 准入（重申 + 强化）

`spec/open/` **仅**允许：

1. **Pending** 产品/探索提案  
2. **Active (draft)** 且已登记进某 `poc/<topic>/ndf/TOPIC.md` 的根提案  
3. 未答 **Q** / 未关闭 **CONFLICT**  
4. 仍指导方向的短 roadmap（非 Implemented 长文）

**MUST** 迁入 `spec/archive/YYYY-MM/`：`Status: Implemented` / `Rejected` / `Superseded`
的提案正文，以及已关闭的 validation/perf 报告。  
`open/` 可留 **Stub — Moved**（一行 Why + Canonical）。

流程/卫生提案仍写 `spec/meta/open/proposal-meta-*.md`（本文件）。

### 2.2 关闭后才 Trunk 回合

| 阶段 | 可改 | 不可改 |
|------|------|--------|
| 探索中 | `poc/`、装订器、Pending/Active 提案、显式 `status=draft` 条款 | `status=stable` 正文；Trunk `src/` 默认路径 |
| 主题关闭 promote | draft→stable 清单 + 干净合入 `src/` + 验证 | 先合代码再补契约 |
| 主题关闭 reject | DEC + deprecated + 归档装订器 | 静默删条款留代码 |

### 2.3 draft ↔ topic 盘点（本轮）

| ID | 文件 | topic_id | 处置 |
|----|------|----------|------|
| [[BEH-021]] | `20-behavior/search.md` | `io-pipelining` | 保留 draft；TOPIC 已登记 |
| [[BEH-022]] | 同上 | `io-pipelining` | 同上 |
| [[BEH-023]] | 同上 | `io-pipelining` | 同上 |
| [[API-010]] | `30-interfaces/env.md` | `io-pipelining` | 同上 |
| [[CON-SLA-013]] | `40-constraints/sla.md` | `io-pipelining` | 同上 |
| [[BEH-024]] | `20-behavior/search.md` | `l4-cache-mgmt` | 保留 draft；提案归档后 stub；TOPIC 仍活 |

**无孤儿 draft。** 修正条款头注释：一律标明 `topic=` 与装订器路径。

### 2.4 本轮归档清单 → `spec/archive/2026-08/`

见落地时 git mv 集合（Implemented/Rejected/validation/perf/phase-c 摘要等）。  
**保留在 open/**：`proposal-io-behavior-correction`、`proposal-4t-scaling-investigation`、
`proposal-io-pipelining`（Active）、`question-learned-pruning`、`optimization-roadmap`。

### 2.5 `models/`

抽检：无 POC 补丁迁入。边界仍 [[ARCH-008]]。

## 3. 非目标

- 本轮不 promote L4 / pipe  
- 不重写稳定搜索契约长文  
- 不改条款 ID

## 4. 落地检查

- [x] 提案写入 `spec/meta/open/`  
- [x] `open/` Implemented 近清零（仅 stub + 活跃面）  
- [x] draft 头含 topic（见 `draft-topic-inventory.md`）  
- [x] MEMORY / AGENTS 纪律口令更新  
