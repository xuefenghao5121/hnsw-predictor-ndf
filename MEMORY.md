# MEMORY.md - OpenClaw 项目记忆

**版本**: v1.1  
**最后更新**: 2026-08-03  
**维护者**: OpenClaw（本仓本地记忆；非 NDF SoT）  
**权威流程**: 以仓库根 `AGENTS.md` + `spec/meta/` 为准；本文件是会话速览，冲突时以规范为准。


## 1. 项目身份

| 属性 | 内容 |
| :--- | :--- |
| 项目名称 | DiskHNSW / `hnsw-predictor-ndf` |
| 项目类型 | 磁盘驻留向量检索库 + NDF 规范驱动棕地工程 |
| 主要语言 | C++（`src/` Trunk）；Python（bench/pipeline/`spec/meta/tools`） |
| 远程 | 常讨论 `git@github.com:xuefenghao5121/hnsw-predictor-ndf.git` |
| 最近提交 | `6809f2a` — meta process profile + `meta/tools` |
| NDF 分层 | 产品 SoT = `spec/00–50`；流程 SoT = `spec/meta/`（[[ADR-META-001]]） |

**一句话描述**: 在 cgroup 内存限额（典型 ≥512MB）下，用磁盘驻留向量做接近全内存 HNSW 的召回（≥95%），Buffered 为优化主目标，O_DIRECT 为诚实验收地板。


## 2. 核心架构指针

### 2.1 规范入口

| 角色 | 路径 |
| :--- | :--- |
| **流程 profile（先读）** | `spec/meta/README.md` → `meta/process.md`（[[CHR-008]]、[[BEH-018]]…[[BEH-025]]） |
| Charter | `spec/00-charter/charter.md`（[[CHR-001]]…；双轨段为 adopted） |
| 架构 | `spec/10-architecture/modules.md`（[[ARCH-008]] 正文在 `meta/architecture.md`） |
| 产品行为 | `spec/20-behavior/`（`search`/`cache`/…；`process.md` 仅为指针） |
| 接口 | `spec/30-interfaces/` |
| SLA / 约束 | `spec/40-constraints/sla.md`（[[CON-SLA-014]] 严格隔离；[[CON-POC-001]] 在 meta） |
| 验收 | `spec/50-verification/` |
| L3 金标 | `spec/models/`（禁 POC 补丁） |
| 审核工具 | `python3 spec/meta/tools/ndf_index.py` → `spec/INDEX.md` |
| 探索轨 | 仓库根 `poc/<topic>/` + `ndf/` 装订器（[[BEH-025]]） |

### 2.2 关键决策索引（摘要）

| 决策ID | 标题 | 状态 |
| :--- | :--- | :--- |
| [[DEC-059]]/[[DEC-062]] | Buffered 主优化 / O_DIRECT 地板 | Accepted |
| [[DEC-061]] | Read Coalescing 负结果（反面教材） | Accepted |
| [[DEC-065]] | 严格 cgroup 隔离 → [[CON-SLA-014]] | Accepted |
| [[DEC-066]] | 废止白嫖 QPS；must vs 观测基线 | Accepted |
| [[ADR-META-001]] | 元规范 vs 产品契约分层 | Accepted（`meta/decisions/`） |
| [[DEC-HYGIENE-001]] / ADR-POC | 卫生与双轨 | 正文在 `spec/meta/decisions/` |

> 产品 DEC：`spec/decisions/`；流程/卫生 ADR：`spec/meta/decisions/`。


## 3. 当前工作状态

### 3.1 活跃会话信息（与 `.openclaw/state.json` 对齐）

- **track**: `poc`
- **当前提案（state）**: `proposal-l4-cache-mgmt.md`（Implemented；主题装订在 `poc/l4-cache-mgmt/ndf/`）
- **validation / perf**: `n/a`（poc 不跑 Trunk SLA）
- **validation_round**: 1 / max 3
- **last_activity**: 2026-08-03T20:01:00Z
- **notes 摘要**: R0–R3 v2 完成；FINE_FADVISE 有害（~17×↓）；L4_EVICT_META ~+3%；Fine I/O 占延迟 95%+；page cache 命中是关键杠杆

### 3.2 进行中的任务

| 任务 | 状态 | 关联 | 备注 |
| :--- | :--- | :--- | :--- |
| L4 page cache 主动管理 | exploring；证据已有 | `poc/l4-cache-mgmt/`、`proposal-l4-cache-mgmt.md`、draft [[BEH-024]] | 待决策：promote EvictMeta / 标注 FADVISE 有害 |
| I/O pipelining 重测 | exploring；旧结论搁置 | `poc/io-pipelining/`、`proposal-io-behavior-correction.md`（**Pending**） | 依赖 L4 稳住后再叠 L5；须 CON-SLA-014 |
| NDF meta 分层 | **已落地** `6809f2a` | `spec/meta/`、AGENTS / harness | process 提案 → `meta/open/proposal-meta-*` |

### 3.3 待处理事项

- [ ] **L4 决策**：是否开 promote 提案合入 `L4_EVICT_META`；是否将 `FINE_FADVISE` 标为有害/负结果（[[BEH-020]]）— 优先级: 高
- [ ] **io-behavior-correction r2**：人工确认 Pending 提案后，严格隔离下重测 pipe — 优先级: 高
- [ ] **4T / DEEP10M**：严格隔离观测基线仍待补全（[[VER-039]] / DEC-066 叙事）— 优先级: 中
- [ ] **推远程**：本地 `main` 曾领先 origin（含 `6809f2a`）；网络/权限允许时 push — 优先级: 低

### 3.4 被阻塞的事项

| 阻塞项 | 阻塞原因 | 解决依赖 |
| :--- | :--- | :--- |
| pipe promote / 旧 DEC-063/064 数字 | 白嫖/EVICT 幽灵口径作废 | L4 进展或独立 C 组 + `proposal-io-behavior-correction` 重测 |
| 部分远端 push | 环境 DNS / `.git/config` busy 曾失败 | 人工网络与权限 |


## 4. 关键约束与规则摘要

### 4.1 技术 / SLA（Trunk must 摘要）

- **测法一等公民**: [[CON-SLA-014]] — `drop_caches` + cgroup；白嫖对照不得作验收
- **召回**: Recall@10 ≥ 95%（SIFT1M 等，见 Charter）
- **RSS / peak / oom**: 见 [[CHR-006]] / [[CON-SLA-011]] 等；**白嫖 era QPS must 已废**（[[DEC-066]]）；Buffered 1T 观测基线约 22.9 等数字只作基线非旧 must 叙事
- **POC 数字不进 production SLA**: [[CON-POC-001]]（`meta/constraints.md`）

### 4.2 流程规则摘要（meta）

- **双轨**: 探索 → `poc/` + draft；晋升 → stable + 干净合入 `src/`（[[CHR-008]]）
- **探索禁**: 直接改 Trunk `src/`；写 stable must SLA（[[BEH-018]]）
- **装订器**: 每主题 `poc/<topic>/ndf/` MUST（[[BEH-025]]）；commit trailers `Topic:` / `Proposals:` / `Clauses:`
- **提案分流**: 产品 → `spec/open/`；process/卫生 → `spec/meta/open/proposal-meta-*.md`
- **Claude Code**: 禁改 `spec/meta/`、charter、architecture、L0/L1（见 `.claude/CLAUDE.md`）

### 4.3 验证闭环状态

| 验证类型 | 最后已知 | 结果 | 报告 |
| :--- | :--- | :--- | :--- |
| 严格隔离基线 | 2026-08-03 | 记录存在 | `spec/open/validation-20260803-strict-baseline.md` |
| 内存优化 promote | 2026-08-02 | pass（追溯） | `validation-20260802.md` / `perf-20260802.md` |
| L4 R0–R3 v2 | 2026-08-03 | POC 自测（非 Trunk SLA） | `poc/l4-cache-mgmt/ndf/` + NOTES |
| pipe 严格重测 | — | 未完成 | 等 behavior-correction |


## 5. 历史决议摘要

### 5.1 重大决策记录

- **2026-08-03**: NDF 元规范整体迁入 `spec/meta/`；`ndf_index` → `spec/meta/tools/`；删除仓库根 `tools/`（`6809f2a`，[[ADR-META-001]]）
- **2026-08-03**: POC 主题装订器 [[BEH-025]] / DEF-022/023（后随 meta）
- **2026-08-03**: 严格隔离升一等公民 [[DEC-065]]/[[CON-SLA-014]]；[[DEC-066]] 废白嫖 QPS must
- **更早**: Read Coalescing 过早合入后证伪 [[DEC-061]] — 双轨反面教材

### 5.2 活跃 POC 主题

| topic | status | 下一闸门 |
| :--- | :--- | :--- |
| `l4-cache-mgmt` | exploring | 决策 EvictMeta promote / FADVISE 负结果 |
| `io-pipelining` | exploring | 等 L4 或独立 C 组；behavior-correction 重测 |


## 6. 下次会话启动引导

> **For OpenClaw**: Session Startup 仍强制读 `AGENTS.md` + `spec/meta/`；本 MEMORY 用于快速对齐「现在做到哪」。

- **重建上下文**: 「DiskHNSW；流程在 `spec/meta/`；产品在 `00–50`；当前 track=poc，焦点 L4（EvictMeta +3% / FADVISE 有害），pipe 待严格重测。」
- **继续 L4**: 读 `poc/l4-cache-mgmt/ndf/TOPIC.md` + `.openclaw/state.json` notes；待用户选 promote 或负结果路径。
- **继续 pipe**: 读 `proposal-io-behavior-correction.md`（Pending）与 `poc/io-pipelining/ndf/TOPIC.md`。
- **流程改动**: track=process → 提案写 `spec/meta/open/proposal-meta-*.md`，勿写回 `20-behavior` 元长文。
- **审核**: `python3 spec/meta/tools/ndf_index.py index|impact|validate|poc-topics`


## 7. 维护记录

| 日期 | 更新内容 | 更新人 |
| :--- | :--- | :--- |
| 2026-08-03 | 按框架初始化：身份、meta 分层、L4/pipe 状态、SLA/流程摘要 | OpenClaw |
| — | 模板骨架 v1.0 | — |
