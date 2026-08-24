# Process 提案：闸漂移必须附带 review-slice diff

> track: process
> Status: Implemented on 2026-08-24
> Reviewed: 已审核
> 日期: 2026-08-24
> 修改: [[META-010]]（增补漂移解释义务）；[[META-011]]（派发 blockers 可读性）；
>       `.cursor/skills/ndf-workflow/`（指挥面报告合同）；工具
>       `ndf_gate_slices` / `poc-dispatch` / `topic-health`
> depends-on: META-008, META-010, META-011, ADR-META-003, ADR-META-004
> refines: META-010, META-011
> 范围: 人审 / 派发被 SHA 拦住时的**可读解释**；不改 SHA 身份钉本身；不恢复面板

## 1. 问题

[[META-010]] 用 review-slice bundle SHA 钉住人审内容身份；[[ADR-META-003]] 保留
「派发」绑定当前契约 SHA 为硬门。这是正确的。

但现行工具在 SHA 不匹配时，指挥面 / `poc-dispatch` / `topic-health` 通常只报：

- `gate_invalidated` / `approved_content_sha` ≠ `expected_content_sha`（两个 hex）
- 失效闸名

人工不知道：

1. **相对哪次批准**发生了漂移；
2. **哪些 review slice** 变了（TOPIC / DESIGN / PERF bind / DELTA 假设 / INTERFACE）；
3. **具体改了什么字**——无法决定「认 → 再说派发」还是「改回去」。

结果是：锁在，说明书不在。人审成本从「读契约」变成「猜哈希」。

## 2. 决策

### P1 — SHA 仍是身份钉；diff 是人审 UI

MUST NOT 用「差不多」「聊天说过」或语义相似度替代 content SHA。  
MUST 在漂移时提供 **相对最近一次有效回执** 的 review-slice 级 diff，使人能完成审核。

### P2 — 漂移解释最小合同（拟写入 [[META-010]]）

当任一 POC 闸（含文字优先 `bundle_dispatch`）相对磁盘当前 bundle 为
`invalidated` / content SHA mismatch 时，指挥面与相关 CLI（至少
`poc-dispatch`、`topic-health`）MUST 产出可读解释，至少含：

| 字段 | 要求 |
|------|------|
| `gate` | 失效闸名 |
| `approved_content_sha` / `expected_content_sha` | 回执 vs 当前（可截断展示，完整值可放 JSON） |
| `changed_slices` | 变更的 `slice_id` + 相对路径列表；未变切片 MUST NOT 喧宾夺主 |
| `slice_diffs` | 每个变更切片的 unified diff（或等价行级 diff）；**仅** `ndf:gate-slice` 内字节 |
| `human_next` | 固定二选一指引：重审后回「派发」；或先改回契约再派发 |

下列 MUST NOT 进入漂移 diff（与 META-010 mutable 面一致）：

- PERF Numbers、DELTA Rounds、`evidence/`、`COMMITS.md`、`GATES.md` 正文追加、
  TOPIC 导航/lifecycle 可变头

若无法还原「批准时切片正文」（缺快照、legacy whole-file 无法对齐 slice）：

- MUST 明确报 `diff_unavailable` + 原因；
- MUST 仍列出当前 slice 指纹 / 路径；
- MUST NOT 静默假装「无变化」或自动重批。

### P3 — 批准时保留可 diff 基线（工具）

为能算出 P2 的 diff，工具在写入 / 校验闸回执时 MUST 能取得批准时刻的 slice 正文，
任选其一（实现可演进，合同要稳定）：

1. **回执旁路快照**：`GATES.md` 同主题目录或 `ndf/evidence/gate-snapshots/` 写入
   按 `approved_content_sha` 索引的 slice 文本包；或
2. **git 锚定**：回执记录 `source_ref` / tree 足以 `git show` 出当时 slice；或
3. **pack 内嵌**：dispatch pack / completion 携带批准切片副本供后续对比。

缺基线 → `diff_unavailable`，不得伪造 diff。

### P4 — 指挥面报告（skill，非面板）

`.cursor/skills/ndf-workflow/`（`poc.md` / `health.md` / `delegate.md`）MUST 规定：

- 人遇 SHA / gate 拦住时，Agent **先展示 slice diff 摘要**，再要人口令；
- 禁止只甩两个 hex 就停；
- 无面板义务：diff 落聊天 + 可选 `tmp/ndf-gate-drift-<topic>.md`（MUST NOT 写入
  `spec/open/`）。

### P5 — 非目标

- 不恢复 Commander / Canvas / Episode 作为人审面；
- 不取消 SHA、不放宽「文件存在=已批准」；
- 不因闸 invalidated **单独**挡住 `ndf_close plan --mode partial|reject`
  （仍遵 META-010 既有例外）；再写码 / 再 `poc-dispatch` 前仍须重过「派发」。

## 3. 拟改条款要点（落地时写入 `process.md`）

在 [[META-010]]「人工门禁回执」下新增小节 **闸漂移解释**：

- invalidated / SHA mismatch → MUST 附 `changed_slices` + slice unified diff（或
  `diff_unavailable`）；
- mutable 面变更 MUST NOT 单独触发该解释路径（因 SHA 本不应变）。

在 [[META-011]] 硬门叙述中补一句：硬阻塞报告 MUST 满足 META-010 漂移解释最小合同，
使人可完成重审，不得仅输出不透明哈希。

新建条款 ID：**不强制**；优先 refine META-010/011。若实现需要独立 must，再用
`{#META-016}`（闸漂移人读解释），`depends-on=META-010,META-011`。

## 4. 工具落点（已确认后）

| 组件 | 动作 |
|------|------|
| `ndf_gate_slices.py` | 增加 `explain_gate_drift(topic, gate) ->` JSON/Markdown |
| `poc-dispatch` | hard block 时 stdout/JSON 含 drift explain；`--json` 带 `slice_diffs` |
| `topic-health` | `gates.*.state=invalidated` 时附 explain 摘要路径 |
| skill | 指挥面遇拦必读 explain 再问人 |

单测：构造批准快照 → 改一处 INTERFACE slice → 断言 diff 含该 hunk、不含 Numbers。

## 5. 验收

- SHA 故意漂移后，`poc-dispatch` / `topic-health` **不以**「仅两个 hex」为唯一输出
- diff **仅**含 review slice；改 Numbers 不产生契约 drift explain
- `diff_unavailable` 路径有明确原因，不自动批准
- `ndf_graphcheck.py --meta` hard_errors=0
- skill 根能一句话说清：拦住时先看 slice diff，再「派发」

## 6. 风险

| 风险 | 缓解 |
|------|------|
| 快照膨胀 | 按 sha 去重；只存 slice 正文；可 gitignore evidence 大包但回执须能解析 |
| legacy whole-file | 明示 `diff_unavailable` + 建议迁移 review_slice |
| diff 过长刷屏 | 聊天默认「变更 slice 列表 + 每片 ≤N 行」；全文进 `tmp/` |

## 7. 冻结

不改产品 `spec/00–50` 检索行为；不强制改 Harness 远程包（本地 SoT 优先）。

## Control receipts

| event | phrase | actor | at | proposal_sha | flow_id | hop | status |
|---|---|---|---|---|---|---|---|
| proposal.confirmed | 已确认 | human | 2026-08-24T15:28:00+03:00 | d1fed7e51520b9c6eee56856631337b3be6c217e7d655f16c4e980b5c2d3c24d | meta-gate-drift-diff | confirm_land | valid |
| proposal.reviewed | 已审核 | human | 2026-08-24T15:39:05+03:00 | d1fed7e51520b9c6eee56856631337b3be6c217e7d655f16c4e980b5c2d3c24d | meta-gate-drift-diff | review | valid |

Process track 已结束；`validation_status` / `perf_status` = `n/a`。无 Trunk 编译/性能验证。
)
