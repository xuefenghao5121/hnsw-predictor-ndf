# Proposal: 方案 A — Buffered 优化主目标闭合 + 探索误改 src 卫生

> track: process
> 关联: [[CHR-001]]、[[CHR-006]]、[[CHR-008]]、[[DEC-059]]、[[DEC-060]]、[[DEC-062]]、
> [[CON-HONEST-002]]、[[CON-SLA-013]]、[[BEH-018]]、[[BEH-021]]、
> `proposal-goal-clarification.md`、`proposal-io-pipelining.md`
> 日期: 2026-08-01
> Status: Implemented on 2026-08-01

## 1. 问题

`proposal-goal-clarification` 已部分落地（CHR-001 追加「优化主目标」、CHR-004 P3），
但 SoT 仍自相矛盾，且落地不完整：

| 位置 | 冲突 / 遗漏 |
|------|-------------|
| CHR-001 | 旧句「优化…地板以 O_DIRECT 为准」与新「Buffered = 优化主目标」并存 |
| CHR-006 / CON-HONEST-002 / DEC-059 | 仍写「优化第一优先级 / 优化优先级 = O_DIRECT」 |
| BEH-021 | 未写明 Buffered 下 pipe_ring_「主动填充 L4」核心价值 |
| CON-SLA-013 / io-pipelining 提案 | 仍以 O_DIRECT 130→140 为主表 |
| NOTES | 缺 §7 基线纪律；未显式禁止引用 v1 不可信数字 |
| 归档 | `spec/open/archive/` 非 `ndf.yaml` 规定的 `spec/archive/` |

另：项目早期探索曾直接改 `src/`（Read Coalescing 合入后证伪；pipelining 后迁 `poc/`）。
流程文档仍有缺口：`AGENTS.md` / `BEH-018` / `.claude/CLAUDE.md` 对「探索禁改 Trunk」不够硬。

## 2. 方案 A（本提案）

1. 新增 **[[DEC-062]]**：修正 [[DEC-059]] 叙事——**Buffered = 生产优化主目标**；
   **O_DIRECT = 诚实验收地板 + 大规模必然磁盘 I/O 路径**（仍独立优化，不假设成果线性惠及 Buffered）。
2. 同步 CHR-001 / CHR-006 / CON-HONEST-002 / DEC-060 措辞（不改 stable QPS 数字）。
3. 补全 BEH-021、CON-SLA-013（Buffered 主表）、io-pipelining 提案与 NOTES。
4. 将 `proposal-goal-clarification` 迁入 `spec/archive/2026-08/`，Status=Implemented。
5. 卫生：`AGENTS.md`、[[BEH-018]]、`.claude/CLAUDE.md`、`poc/README.md` —
   明确探索 MUST 落在 `poc/`；误改 `src/` 的矫正检查清单；归档路径。

## 3. 落地清单（Implemented）

| 文件 | 变更 |
|------|------|
| `spec/decisions/05-odirect-floor.md` | +DEC-062；DEC-059/060 amended-by |
| `spec/00-charter/charter.md` | CHR-001/006 统一 Buffered 主目标 |
| `spec/40-constraints/sla.md` | CON-HONEST-002；CON-SLA-013 Buffered 主表 |
| `spec/20-behavior/search.md` | BEH-021 Buffered 填 L4 |
| `spec/20-behavior/process.md` | BEH-018 第 6 条禁改 src |
| `spec/open/proposal-io-pipelining.md` | r3 |
| `poc/io-pipelining/NOTES.md` | §7 + v1 INVALIDATED |
| `spec/archive/2026-08/proposal-goal-clarification.md` | 正确归档 |
| `AGENTS.md` / `.claude/CLAUDE.md` / `poc/README.md` / `skills/ndf-workflow` | 双轨卫生 |

## 4. 不做的事

- 不改 [[CHR-006]] / [[CON-SLA-011]] 的 stable QPS 数字
- 不 promote pipe_ring_；不把 POC 数字写入 must SLA
- 不重写已推送 git 历史
