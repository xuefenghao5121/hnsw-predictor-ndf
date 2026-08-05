# Proposal: NDF 规范文件群防腐化与优化 {#PROP-NDF-HYGIENE}

> Status: Implemented on 2026-07-31
> 场景: 场景3（项目重构 / 规范整治）
> 日期: 2026-07-31
> 关联 ADR: [[adr-ndf-hygiene.md]] / `{#DEC-HYGIENE-001}`

## 动机

本地 `spec/` 目录骨架完整，但相对 NDF 设计纪律处于**结构性腐化**：

1. **ID 图损坏**：`{#CHR-003}`/`{#CHR-004}`、`{#ARCH-001}`/`{#ARCH-004}` 各撞车一次；`OBS-*`/`INTENT-*` 残留引用；`DEC-039` 被多处引用但正文不存在（`DEC-038` 跳到 `DEC-057`）。
2. **元数据不合规**：大量把 `layer=L0/L1` 写进 `level=`；`status=exploratory` 非法；`ndf.yaml` 的 `id-prefixes: [OBS]` 与真实前缀脱节。
3. **语义过期**：Charter 无模式限定的 QPS≥2000 与 [[CON-HONEST-002]] / `validation-odirect-20260731.md`（O_DIRECT 130 QPS）冲突；[[DEC-027]] 未标记被后续 O_DIRECT 决策 supersede。
4. **`open/` 失真**：约 15/20 文件已落地或过时，仍占“开放”位。

## 执行原则

- OpenClaw 写入：`00/`、`10/`、`20`(L0–L1)、`30`(协议)、`40/`、`decisions/`、`open/`、`archive/`
- Claude Code 写入：`50-verification/`、L2/L3 元数据与 `refines` 链、glossary 术语补全中的 L2 段
- 归档不删除：迁入 `spec/archive/2026-07/`
- SLA：**双轨**——Buffered 保留现有阈值；Honest/O_DIRECT 写入实测下限（以 2026-07-31 报告为准）

---

## A1. 消除重复 ID（固定映射）

| 现状 | 新 ID | 文件 | 动作 |
|------|-------|------|------|
| Non-Goals `{#CHR-003}` | 保持 `CHR-003` | `00-charter/charter.md` | 不变 |
| 关键性能承诺 `{#CHR-003}` | → `CHR-006` | 同上 | 重编号 + 模式限定 QPS |
| 演进路线 `{#CHR-004}` | 保持 `CHR-004` | 同上 | `status=draft`，去掉非法 `exploratory` |
| 设计约束硬条款 `{#CHR-004}` | → `CHR-007` | 同上 | 重编号；[[CHR-005]] 内 `[[CHR-004]]` → `[[CHR-007]]` |
| 模块依赖图 `{#ARCH-001}` | 保持 | `10-architecture/modules.md` | 不变 |
| 远期架构 `{#ARCH-001}` | → `ARCH-006` | 同上 | 重编号；删 INTENT 残留文案 |
| 关键耦合 `{#ARCH-004}` | 保持 | 同上 | 不变 |
| 技术债务 `{#ARCH-004}` | → `ARCH-007` | 同上 | 重编号；SoT for CONFLICT-002 |

交叉引用批量更新：凡引用旧撞车语义者，按上表改写。

## A2. 幽灵决策、清单与死链

### DEC-039 物化

在 `spec/decisions/p2-decisions.md`（`DEC-038` 之后）落盘：

```markdown
## D-039: 诚实 I/O 测量协议 {#DEC-039}
<!-- ndf: kind=decision date=2026-07-30 status=stable since=0.4
     affects=DEC-021,DEC-030,CON-HONEST-002 source=deduced -->

**Context.** 仅报告 Buffered QPS 会把 OS page cache 收益计入产品性能，
造成 cgroup 预算与真实 I/O 成本失真。

**Decision.**
1. 基准测试 MUST 支持诚实测量路径：`drop_caches` + 可选 `posix_fadvise(DONTNEED)`
   （查询间驱逐），以及 `FINE_DIRECT=1`（O_DIRECT，查询内绕过 page cache）。
2. 报告 MUST 同时给出 Buffered 与 Direct（或明确标注单模式及其局限）。
3. 本决策由 [[CON-HONEST-002]] 契约化；实测结果见 [[DEC-057]]。

> rationale: 诚实协议先于 O_DIRECT 水分量化；DEC-057 是本协议的执行证据。
```

`CON-HONEST-002` 的 `refines: DEC-030, DEC-039` 保持不变（目标 ID 将真实存在）。

### ndf.yaml 重写

```yaml
id-prefixes: [CHR, DEF, ARCH, BEH, API, CON, VER, DEC, Q, CONFLICT]
```

保留 `source=observed` 说明。

### DEC-027 supersede

```
status=superseded-by=DEC-030
```

正文追加：第 3 点“当前不引入 O_DIRECT”已被 [[DEC-030]]（FINE_DIRECT 诊断）与 [[DEC-039]]/[[DEC-057]]（诚实基准）取代；SPDK/P3 评估意图由 DEC-030 §4 继承。

### OBS / INTENT 死链重定向

| 旧引用 | 新目标 |
|--------|--------|
| `OBS-BEH-*` | `BEH-*`（同号） |
| `OBS-ARCH-*` / `OBS-API-*` / `OBS-DEF-*` / `OBS-CON-*` | 去前缀同号 |
| `OBS-DEC-*` | `DEC-*` |
| `INTENT-CHR-003` | `CHR-006` |
| `INTENT-ARCH-004` | `ARCH-007` |
| `INTENT-ARCH-003`（已删除） | 删除 affects 或改为 `ARCH-005` |
| 正文中的 `INTENT-ARCH-004` 叙述 | 改为 `ARCH-007` |

## A3. SLA / Charter 调和（L1）

### CHR-006（原重复性能承诺）双轨

| 指标 | Buffered（`FINE_BUFFERED=1`） | Honest / O_DIRECT（`FINE_DIRECT=1`） |
|------|------------------------------|-------------------------------------|
| Recall@10 | ≥ 95% | ≥ 95% |
| QPS (1T) | ≥ 2000 | ≥ 100（实测下限，2026-07-31：130） |
| QPS (4T) | ≥ 5000 | ≥ 400（实测下限，2026-07-31：502） |
| RSS | ≤ 300MB | ≤ 300MB |
| 内存节省 | ≥ 2.5x vs hnswlib | 同左 |

报告 MUST 标注 I/O 模式；仅报 Buffered 时 MUST 附 [[CON-HONEST-002]] 声明。

### 新增 CON-SLA-011

```markdown
## Honest / O_DIRECT QPS 下限 {#CON-SLA-011}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.5
     refines=CON-HONEST-002 depends-on=DEC-039,DEC-057 -->

SIFT1M、512MB cgroup、`FINE_DIRECT=1` 下：
- 单线程 QPS MUST ≥ 100
- 四线程 QPS MUST ≥ 400
Recall@10 MUST ≥ 95%（与 Buffered 相同）。
```

Buffered 侧既有 `CON-SLA-008`…`010` 与 Charter Buffered 行保持；不静默删除旧数字。

### Recall 94 / 95

- SoT：Charter / CON ≥ **95%**
- [[DEC-029]] §3 “Recall ≥94%” 标注为 **P2 过渡验收**（`status` 说明或正文标注），不覆盖 Charter
- P2 验证表中的 ≥94% 行保留为历史证据，标注 “P2 transitional”

### BEH-015 deprecated

[[DEC-024]] 已正式放弃 Dynamic Width → `BEH-015` / `BEH-015-L2`：`status=deprecated`，`depends-on=DEC-024`。

### 元数据规范化（固定目录扫描）

- `level` ∈ `{must,should,may,tbd}`；`layer` ∈ `{L0,L1,L2,L3}`
- 修复：`CON-SLA-008/009/010` 的 `level=L1` → `level=must|should|info` + `layer=L1`
- `BEH-014`/`API-007`/`CON-007`：已交付实验功能 → `status=stable`（opt-in）；`BEH-015` → `deprecated`

## A4. open/ 归档表

### 迁入 `spec/archive/2026-07/`

| 文件 | 处置 |
|------|------|
| `proposal-fine-rerank-io-optimization.md` | Implemented → archive |
| `proposal-cold-io-mode.md` | Implemented → archive |
| `proposal-odirect-benchmark.md` | Implemented → archive |
| `proposal-sla-adjust-ps-dw.md` | 先改 Status: Implemented，再 archive |
| `proposal-direct-io.md` | 顶部标注 `superseded-by=DEC-030,DEC-057` → archive |
| `comparison.md` | Resolved → archive |
| `question-scale-boundary.md` | 已关闭/过时 → archive |
| `validation-*.md`（全部，含 odirect） | archive |
| `perf-*.md`（全部） | archive |
| `conflict-vec-only-detection.md` | CONFLICT-001 提升后 archive（Resolved） |
| `conflict-header-size.md` | SoT=`ARCH-007`，status=resolved → archive |

### 保留在 `open/`

| 文件 | 原因 |
|------|------|
| `question-learned-pruning.md` | Q-002 未关闭 |
| `optimization-roadmap.md` | 活路线图 |
| `proposal-ndf-hygiene.md` | 本提案（落地后改 Implemented 并可后续归档） |

### CONFLICT 提升

**CONFLICT-001 → L1 澄清**

- [[API-004]]：补充 VecOnly header 布局  
  `[block_id:u32][node_count:u32][data_offset:u32][flags:u32]`（16B），与标准 BlockHeader（24B，`flags:u8@16`）区分。
- [[BEH-009]]：增加 L1 判定契约——`parseBlock` MUST 先按 VecOnlyHeader 在 offset 12 读 `flags:u32` 检测 `FLAG_VEC_ONLY`；仅当未置位时再按标准 BlockHeader 解析。误判风险与缓解写入 rationale。

**CONFLICT-002 → 债务 SoT**

- 硬编码 `4096ull` 债务以 [[ARCH-007]] 为唯一 SoT；冲突文件归档并 `status=resolved`。

## 阶段 C — 委派 Claude Code（验收层与 L2）

指令要点（ACP `d21779ab-aad3-408c-a717-f871eae0884e`）：

1. 修复 `50-verification/tests.md` / `p2-verification.md`：`verifies=` 从死 `OBS-*` 改到真实 `BEH-*`/`CON-*`；补齐稀疏 VER 元数据。
2. 为 `BEH-003`…`BEH-013` 补 `refines=` → `BEH-001`/`BEH-002`（禁止 `refines=DEC-*`）。
3. 冷 I/O 无 ID 验证表补 `{#VER-…}`。
4. 对齐 `VER-030`：区分 Buffered diagnostic vs Honest O_DIRECT（消除 787 vs 130 双重真相）。
5. glossary 补：Page Search、Dynamic Width、FINE_DIRECT、Honest I/O、cgroup MemoryMax 等。
6. 输出 must 级 L1 的 VER 覆盖摘要（允许列残余缺口，禁止死 ID）。

## 阶段 D — 防再腐化门禁（ADR 固化）

1. 禁止新条款复用已有 `{#ID}`（落地前 grep）。
2. `open/` 仅保留 Pending / 未回答 Q / 未关闭 CONFLICT；Implemented 必须归档。
3. 任何 SLA 数字变更必须同时改 `40-constraints/` + Charter 引用 + 一条 DEC/ADR。
4. 决策编号连续；跳号必须有占位或 gap 说明。

## 非本轮范围

- 不重写全部 L2 为外部契约；不新建 `models/`；不改 `src/`；不重跑全量压测。
- SLA 条款变更落地后，再视需要触发场景 5/6。

## 验收标准

- [ ] 固定目录无重复 `{#ID}`
- [ ] 无悬空 `OBS-*` / `DEC-039` / 活 `INTENT-*` 引用
- [ ] `ndf.yaml` 前缀覆盖实际 ID
- [ ] Charter QPS 与 `CON-HONEST-002` / `CON-SLA-011` 无矛盾
- [ ] `open/` ≤ 活跃少数文件；历史证据在 `archive/2026-07/`
- [ ] must 级 L1 的 `verifies=` 覆盖率可枚举（无死 ID）

## 变更影响摘要

| 区域 | 变更类型 |
|------|----------|
| `00-charter/` | CHR 重编号 + 双轨 SLA + glossary（委派补术语） |
| `10-architecture/` | ARCH 重编号 + INTENT 文案清理 |
| `20-behavior/` | BEH-009 L1 澄清；BEH-015 deprecated；BEH-014 stable |
| `30-interfaces/` | API-004 VecOnly；API-007 stable |
| `40-constraints/` | CON-SLA-011；元数据；CON-007 stable |
| `decisions/` | DEC-039 物化；DEC-027 supersede；DEC-029 P2 过渡标注 |
| `open/` → `archive/` | 见 A4 表 |
| `50-verification/` | 委派 Claude Code |
