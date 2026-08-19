# MEMORY.md - OpenClaw 项目记忆

**版本**: v1.4  
**最后更新**: 2026-08-06  
**维护者**: OpenClaw（本仓本地记忆；非 NDF SoT）  
**权威流程**: 以仓库根 `AGENTS.md` + `spec/meta/` 为准；本文件是会话速览，冲突时以规范为准。


## 1. 项目身份

| 属性 | 内容 |
| :--- | :--- |
| 项目名称 | DiskHNSW / `hnsw-predictor-ndf` |
| 项目类型 | 磁盘驻留向量检索库 + NDF 规范驱动棕地工程 |
| 主要语言 | C++（`src/` Trunk）；Python（bench/pipeline/`spec/meta/tools`） |
| 远程 | `git@github.com:xuefenghao5121/hnsw-predictor-ndf.git` |
| 最近工作 | SLA↔env 图依赖 + `trunk-ref`（META-005）；工作流文档同步；Harness 冻结待统一重提炼 |
| NDF 分层 | 产品 SoT = `spec/00–50`；流程 SoT = `spec/meta/`（[[ADR-META-001]]） |
| 远程状态 | 38 个文件（纯代码+脚本+文档）；gitignored 文件已从远程清除 |

**一句话描述**: 在 cgroup 内存限额（典型 ≥512MB）下，用磁盘驻留向量做接近全内存 HNSW 的召回（≥95%），Buffered 为优化主目标，O_DIRECT 为诚实验收地板。


## 2. 核心架构指针

### 2.1 规范入口

| 角色 | 路径 |
| :--- | :--- |
| **流程 profile（先读）** | `spec/meta/README.md` → `language.md`（[[META-001]]…[[META-005]] / `trunk-ref`）→ `process.md`（[[CHR-008]]、[[BEH-018]]…[[BEH-025]]） |
| Charter | `spec/00-charter/charter.md`（[[CHR-001]]…；双轨段为 adopted） |
| 架构 | `spec/10-architecture/modules.md`（[[ARCH-008]] 正文在 `meta/architecture.md`） |
| 产品行为 | `spec/20-behavior/`（`search`/`cache`/…；`process.md` 仅为指针） |
| 接口 | `spec/30-interfaces/`（env：[[API-011]]…[[API-013]] + `trunk-ref`） |
| SLA / 约束 | `spec/40-constraints/sla.md`（[[CON-SLA-014]]；[[CON-POC-001]] 在 meta；性能 SLA 须图连 API，见 [[META-005]]） |
| 验收 | `spec/50-verification/` |
| L3 金标 | `spec/models/`（禁 POC 补丁） |
| 审核工具 | `python3 spec/meta/tools/ndf_index.py` -> `spec/INDEX.md` |
| 回合工具 | `python3 spec/meta/tools/ndf_close.py plan --topic <t> --mode partial\|promote\|reject` |
| 探索轨 | 仓库根 `poc/<topic>/` + `ndf/` 装订器（[[BEH-025]]） |
| Portable Harness | `packages/ndf-harness/` — **冻结**，待统一重提炼；不以包为本地 SoT |
| 冷存储 | `spec/archive/2026-08/`（Implemented open 正文） |

### 2.2 关键决策索引（摘要）

| 决策ID | 标题 | 状态 |
| :--- | :--- | :--- |
| [[DEC-059]]/[[DEC-062]] | Buffered 主优化 / O_DIRECT 地板 | Accepted |
| [[DEC-061]] | Read Coalescing 负结果（反面教材） | Accepted |
| [[DEC-065]] | 严格 cgroup 隔离 -> [[CON-SLA-014]] | Accepted |
| [[DEC-066]]/[[DEC-067]] | 白嫖废止 / 假基线修正（PQ_CODES_PATH 拼写） | Accepted |
| [[DEC-068]] | flat_vec_cache + O_DIRECT 4T fix promote | Accepted |
| [[DEC-069]] | flat_vec_cache cap fix promote | Accepted |
| [[DEC-070]] | WILLNEED readahead hint promote | Accepted |
| [[ADR-META-001]] | 元规范 vs 产品契约分层 | Accepted |
| [[DEC-HYGIENE-001]] | 卫生与 open 准入 | Accepted（`meta/decisions/`） |

> 产品 DEC：`spec/decisions/`；流程/卫生 ADR：`spec/meta/decisions/`。


## 3. 当前工作状态

### 3.0 节奏口令（必记）

```text
Trunk NDF 收口 -> POC 实验（poc/ + draft）-> 主题关闭才 NDF/src 回合
```

探索中：**默认不改** `status=stable` 与 Trunk `src/`。  
关闭时：promote（draft->stable + 干净合入）或 reject（DEC + deprecated）。

### 3.1 活跃 `spec/open/`

| 文件 | 状态 |
| :--- | :--- |
| `proposal-io-behavior-correction.md` | Pending |
| `proposal-4t-scaling-investigation.md` | Pending |
| `proposal-io-pipelining.md` | Superseded (DEC-071) |
| `question-learned-pruning.md` | Q |
| `optimization-roadmap.md` | 方向摘要 |
| `validation-20260804.md` | 场景5 编译验证报告（WILLNEED） |
| `perf-20260804.md` | 场景6 性能验证报告（WILLNEED） |
| 若干 Stub - Moved | 指向 `archive/2026-08/` 或 meta |

卫生提案：`spec/meta/open/proposal-meta-trunk-hygiene-r2.md`；draft 盘点：`draft-topic-inventory.md`。

### 3.2 进行中的 POC

| 任务 | 状态 | 关联 | 备注 |
| :--- | :--- | :--- | :--- |
| L4 page cache | exploring（WILLNEED 已 promoted） | `poc/l4-cache-mgmt/`、BEH-024(stable) | R5b Selective DONTNEED 仍 POC；R5c mincore 未做 |
| I/O pipelining | **rejected** (DEC-071) | `poc/io-pipelining/`（归档） | WILLNEED 取代 pipe_ring_；BEH-021/022/023/API-010/CON-SLA-013 deprecated |
| ~~pq-quality~~ | **rejected** (DEC-072) | `poc/pq-quality/`（归档） | M=32 是 SLA 达标唯一选择, OPQ 破坏图搜索 |
| ~~refine-ef-tuning~~ | **rejected** (DEC-072) | `poc/refine-ef-tuning/`（归档） | EF=300 是 Recall≥95% 硬约束 |

### 3.3 待处理事项

- [x] **L4 WILLNEED promote** -> 已完成（DEC-070, BEH-024 amend, API-012）
- [x] **推远程** -> 已完成（14 commits, gitignored 文件已清除）
- [ ] **L4 Selective DONTNEED 决策**：promote 或 close（R5b 仅 +14%，场景有限）- 低
- [x] **io-behavior-correction**：确认 Pending 后严格隔离重测 - 高 -> 完成，负结果闭环
- [ ] **4T / DEEP10M** 严格基线补全 - 中

### 3.4 被阻塞

| 阻塞项 | 原因 | 依赖 |
| :--- | :--- | :--- |
| pipe promote | 旧口径作废 | L4 已 promote；还需 behavior 重测 |


## 4. 关键约束与规则摘要

### 4.1 技术 / SLA

- [[CON-SLA-014]] 测法一等公民；白嫖不作验收
- Recall@10 ≥ 95%
- 严格隔离 Buffered 1T 观测基线须正确 `PQ_CODES_PATH`（~2309；**旧 22.9 为假基线**）
- [[CON-POC-001]]：POC 数字不进 production must
- SIFT1M 512MB SLA: QPS ≥ 2000 (1T) / ≥ 5000 (4T), Recall ≥ 95%, RSS ≤ 300MB

### 4.2 流程

- 双轨 + 装订器；提案分流 open vs meta/open
- **open 不堆 Implemented**（-> `archive/`）
- Claude 禁改 meta / L0–L1
- promote 后 MUST 跑 ndf_close.py + ndf_index.py + ndf_graphcheck.py
- stable MUST NOT refines/depends-on draft（ndf_graphcheck 检查）

### 4.3 验证报告位置

| 报告 | 路径 |
| :--- | :--- |
| 严格隔离基线 | `spec/archive/2026-08/validation-20260803-strict-baseline.md` |
| 内存 promote | `spec/archive/2026-08/validation-20260802.md` 等 |
| WILLNEED 编译验证 | `spec/open/validation-20260804.md` |
| WILLNEED 性能验证 | `spec/open/perf-20260804.md` |
| L4 R0–R5 全部 | `poc/l4-cache-mgmt/ndf/TOPIC.md` |


## 5. 历史决议摘要

- **2026-08-04**: io-pipelining 负结果闭环（DEC-071）；BEH-021/022/023/API-010/CON-SLA-013 deprecated；根因 = WILLNEED 取代 pipe_ring_
- **2026-08-04**: R5 实验：WILLNEED 17.7x@256MB / +5.5%@512MB / ~0%@DEEP10M；Selective DONTNEED +14%（保持 POC）
- **2026-08-03**: Trunk open 卫生收口 r2 -> `archive/2026-08/`
- **2026-08-03**: meta process profile + `meta/tools`（`6809f2a`）
- **2026-08-03**: BEH-025 装订器；DEC-065/066/067；DEC-066 假基线修正
- **2026-08-03**: DEC-068 flat_vec_cache + O_DIRECT 4T fix promote
- **更早**: DEC-061 RC 负结果

### 活跃 POC 主题

| topic | draft 条款 | 下一闸门 |
| :--- | :--- | :--- |
| `l4-cache-mgmt` | BEH-024(stable, WILLNEED promoted) | R5b SelDONTNEED close 或 R5c mincore |
| `io-pipelining` | BEH-021…023, API-010, CON-SLA-013 (all deprecated) | **rejected** (DEC-071) |
| `pq-quality` | (in TOPIC) | promote 决策 |
| `refine-ef-tuning` | (in TOPIC) | promote 决策 |


## 6. WILLNEED 技术要点（必记）

### 机制
`posix_fadvise(POSIX_FADV_WILLNEED)` 在 fine rerank pread 循环前对所有 `pages_needed` 调用，内核启动异步 readahead。pread 从阻塞磁盘 I/O 变为内存拷贝。

### 适用条件
1. page cache 严重受限（budget << hot working set）
2. pread 是 query 延迟的主要来源
3. refault 暴涨证明 LRU 在误杀热页

### 跨场景效果

| 场景 | WILLNEED 效果 | 原因 |
|------|-------------|------|
| SIFT1M 256MB | **17.7x QPS** | pread 是瓶颈，readahead 消除串行等待 |
| SIFT1M 512MB | +5.5%（无回归） | pread 非瓶颈 |
| DEEP10M 2GB | ~0%（中性） | I/O 量是瓶颈（68K majfault），非时序 |

### cgroup 合规
- `memory.peak` = cgroup limit（从未超过）
- `file` = 103MB（与基线相同，WILLNEED 不多用内存）
- `majfault` 不变（I/O 量不减少，只改变时序）
- `oom` = 0

### 代码位置
`src/core/disk_hnsw.cpp:1754-1761`（+8 行，env `L4_WILLNEED=1`，默认关闭）


## 7. 下次会话启动引导

- **节奏**: 先确认 open 够薄 -> 只动 POC -> 关闭才回合 Trunk。
- **L4**: `poc/l4-cache-mgmt/ndf/TOPIC.md`（WILLNEED promoted，SelDONTNEED 仍 POC）
- **pipe**: `proposal-io-behavior-correction.md` + io TOPIC
- **process**: `spec/meta/open/proposal-meta-*.md`
- **审核**: `python3 spec/meta/tools/ndf_index.py index` + `ndf_graphcheck.py`
- **回合**: `python3 spec/meta/tools/ndf_close.py plan --topic <t> --mode partial|promote|reject`


## 8. 维护记录

| 日期 | 更新内容 | 更新人 |
| :--- | :--- | :--- |
| 2026-08-04 | v1.3：WILLNEED promote 完成、R5 实验结果、ndf_close 回合、远程清理 | OpenClaw |
| 2026-08-03 | v1.2：卫生收口 r2、open 活跃面、关闭后才回合口令 | OpenClaw |
| 2026-08-03 | v1.1：框架初始化 | OpenClaw |
