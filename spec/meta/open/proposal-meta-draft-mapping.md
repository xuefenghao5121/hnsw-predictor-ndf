# Process 提案：Draft 状态并发映射（探索→晋升受控路径）

> track: process
> Status: Implemented on 2026-08-17
> reviewed: 已审核
> 日期: 2026-08-17
> 修改: BEH-018, BEH-019
> depends-on: CHR-008, BEH-018, BEH-019, DEF-021, DEF-022, ARCH-008, META-010
> 范围: NDF Draft 状态映射 / 晋升闸门 / 提案 hygiene

## 1. 问题

NDF 是唯一事实源（SoT），探索轨与主线轨的区分靠条款的 `status`
（`draft` / `stable`）刻画（[[CHR-008]] / [[BEH-018]] / [[DEF-021]]）。

但探索中的不确定性是**持续演进的**：一次探索可能反复改假设、接口、绑定配置，
产生多版契约草稿（v1→v2→…）。若把这些演进的 `status=draft` 数量、版本、依赖
面直接写在 8 个固定模块（`00-charter` / `10-architecture` / `20-behavior` /
`30-interfaces` / `40-constraints` / `50-verification` / `decisions/` /
`models/`）内，会造成三类污染：

1. **正文污染**：固定模块正文被迫承载"尚未批准"的条款，stable must 与 draft
   混排，读者无法一眼区分"已批准的稳定性"与"探索中的不确定性"（[[DEF-NDF-STABLE-DRAFT]]）。
2. **晋升污染**：`draft→stable` 的晋升（[[BEH-019]]）在正文上就是"改一行 status"，
   没有独立的、可审计的映射面，晋升链路（哪些 draft、绑定哪个 TOPIC、引用哪份
   提案/证据）散落在正文注释里，无法机械核验。
3. **回退污染**：负结果（[[BEH-020]]）要求撤 draft，正文上又是"删/改 status"，
   历史被抹平，无法追溯某个 draft 曾绑定过的探索主题。

结论：Draft 状态不应是固定模块正文的字段，而应是一层**与正文正交的、文件系统
侧的并发映射**，把"探索中的不确定性"从"已批准的稳定性"里物理分离出来。

## 2. 决策

1. 固定 8 模块正文 MUST 只承载 `status=stable` 的产品条款；`status=draft` 条款
   的**存在与演进状态** MUST 由文件系统侧映射承载，MUST NOT 以正文 status 字段为
   Draft 状态的唯一事实源。
2. 映射落点 MUST 独立于 8 模块正文：`spec/meta/open/draft-map/`（本提案新增的
   映射目录；流程 SoT，非产品契约树）。映射文件与固定模块正文并发存在，二者
   MUST NOT 交叉写回。
3. 映射条目（每条对应一个 draft 条款 ID）MUST 至少记录：

   ```text
   clause_id / topic / topic_ndf / proposed_status / refs / sha
   ```

   - `clause_id`：draft 条款 ID（或拟新增稳定条款的目标 ID）。
   - `topic`：绑定 `poc/<topic>/`（探索）或 `meta` workflow 主题（流改进）。
   - `topic_ndf`：绑定装订器 `TOPIC.md` 路径（[[DEF-022]] / [[BEH-025]]）。
   - `proposed_status`：`exploring`（探索中）/ `closing`（晋升编排中，见 [[BEH-019]]）。
   - `refs`：承载该 draft 的提案 / DEC / 证据指针。
   - `sha`：映射条目内容哈希，供门禁回执（[[META-010]]）校验是否漂移。
4. 晋升（[[BEH-019]]）MUST 以映射条目为受控路径：
   - 条目 `proposed_status: exploring → closing` 由提案确认触发；
   - 全部闸门通过后，映射条目归档（`spec/meta/open/draft-map/archive/` 或等效
     摘要指针），固定模块正文**才**写入对应 `status=stable` 条款；
   - MUST NOT 在映射条目仍 `exploring` 时把正文写成 stable（禁止先合主线再补契约）。
5. 负结果 / 回退（[[BEH-020]]）MUST 在映射面关闭条目（`proposed_status` 标回退 /
   归档），MUST NOT 靠静默删除映射条目抹平历史。
6. 映射面 MUST NOT 伪装为产品契约树：`spec/meta/open/draft-map/` 是 Control 流程
   映射，不是 Trunk SoT；stable must 仍只在 `spec/00–50`（[[ARCH-008]]）。

## 3. 变更

- new `spec/meta/open/draft-map/README.md`：映射目录语义与条目 schema（本提案新增，
  process 平面）。
- [[BEH-018]] 第 1 款补一句话：draft 状态由并发映射承载，正文 status 字段不单独
  充当 Draft 事实源（见本提案）。
- [[BEH-019]]：晋升受控路径补"映射条目 `exploring → closing` → 归档 → 正文写
  stable"顺序。
- `spec/meta/tools/ndf_workflow_status.py`：`scan_proposals()` / draft 扫描新增
  映射一致性检查；draft 条目无对应映射行时记 `draft_map_warnings`（warning，非
  hard_error），避免破坏既有绿地操作。

## 4. 验收

1. 固定 8 模块正文不含 `status=draft` 且无映射的条款（`draft_map_warnings` 为空或
   可归因）。
2. 每个 `status=draft` 条款在 `draft-map/` 有一条目，且 `sha` 可回溯。
3. 晋升链路可审计：条目 `exploring → closing → archived`，正文 stable 写入不早于
   映射归档。
4. 负结果回退后映射条目保留（归档/标回退），不静默删除。
5. `python3 spec/meta/tools/ndf_graphcheck.py --meta` hard_errors=0。
6. Canvas 不手改映射行，只重嵌官方 `canvas-json` SNAPSHOT。

## 5. 不做（本轮边界）

- 不落地任何 `status=draft` 条款的正文写入或晋升（仅提案级）：只引入映射机制。
- 不修改 8 固定模块正文（`spec/00–50`、`decisions/`、`models/`）任何现有 stable
  条款。
- 不批门禁、不伪造 `approved_by`、不写 `.openclaw/state.json`。
- 不实现映射目录的实际内容生成；本条正文为提案级描述，具体 schema 由后续
  process proposal 落地。
