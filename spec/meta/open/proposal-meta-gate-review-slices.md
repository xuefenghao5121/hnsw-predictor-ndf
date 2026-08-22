# Process 提案：POC 门禁审核切片与 SHA 稳定化

> track: process
> refines: META-010, META-011, META-012, META-013
> depends-on: META-008, META-010, META-011, META-012, META-013
> Status: Implemented on 2026-08-13

## 背景

POC 门禁的目的，是让人口令绑定当时审核过的**契约内容**，不是冻结整份探索日志。
现行工具把 TOPIC、DESIGN、PERF_BASELINE、DELTA、INTERFACE 整文件拼成 canonical
bundle。该策略比 [[META-010]] 更宽：META-010 对实现许可只要求
`PERF_BASELINE` 绑定头与 `DELTA` 假设，但整文件哈希会把正常的 Numbers、Rounds、
evidence 追加也解释为契约漂移，导致三闸反复失效。

同时，实际 Control 回合曾由 OpenClaw 越过角色边界写入性能 Numbers 与 DELTA
measurement round。按 [[META-011]]，这些测量产物属于 Claude Code / evidence 流；
仅有文档数字、无 run/lease/measure/evidence 回执，不能恢复 baseline current 或使
关闭/实现状态变绿。

## 目标

1. 门禁 SHA 绑定显式 `review_slice`，而不是无差别整文件。
2. 契约修改继续 fail closed；实验进度/证据追加不制造无意义重审。
3. 明确 Gate、Binder/OpenClaw、Claude Code 的 section-level 写入所有权。
4. 旧 whole-file receipt 不静默升级为 review-slice receipt。
5. 对越权产生的测量数字做 evidence 审计，不删历史、不默认采信。

## 拟修改 [[META-010]]

### Review slice

新建/迁移后的 POC 门禁 bundle MUST 由显式审核切片组成。切片标记 MUST：

1. 在同一文件内成对出现、ID 唯一、不可嵌套；
2. begin/end 之间字节按原样参与 SHA；
3. canonical 输入为：

   ```text
   slice_id NUL repo_relative_path NUL slice_bytes NUL
   ```

4. bundle 中切片按 `slice_id + path` 排序后计算 SHA-256。

推荐标记：

```markdown
<!-- ndf:gate-slice begin=topic_contract -->
... reviewed contract ...
<!-- ndf:gate-slice end=topic_contract -->
```

门禁切片：

| gate | canonical review slices |
|------|-------------------------|
| `topic_review` | TOPIC intent / scope / hypothesis / directions / proposal contract |
| `design_review` | topic contract + DESIGN goals/non-goals/modules/data-flow/trunk-boundary/design contract |
| `implementation_approval` | 上述 contract + PERF bind header + DELTA hypothesis + INTERFACE contract |

### Mutable 内容

下列内容 MUST 在 review slice 外；只追加它们 MUST NOT 改变三闸 SHA：

- TOPIC lifecycle 导航、`baseline_status`、`baseline_trunk_sha`、`next_gate`
- PERF `Numbers` / measurement result
- DELTA `Rounds` / measured outcome
- `evidence/`、`COMMITS.md`、`GATES.md`

若 mutable 内容反向修改假设、接口、绑定配置或实现边界，MUST 先修改对应 review slice，
从而触发正确门禁失效，禁止借“结果追加”绕过重审。

### 失效矩阵

| changed review slice | invalidated gates |
|----------------------|-------------------|
| TOPIC contract | topic_review, design_review, implementation_approval |
| DESIGN contract | design_review, implementation_approval |
| PERF bind / DELTA hypothesis / INTERFACE contract | implementation_approval |
| Numbers / Rounds / evidence / COMMITS / GATES | none |

缺标记、重复标记、错配或嵌套 MUST fail closed。旧主题 MAY 暂时显示
`bundle_mode=legacy_whole_file`；迁移必须追加 invalidated/迁移说明并重新审核，
不得把旧 SHA 当成新切片 SHA。

## 拟修改 [[META-011]]

### Section-level ownership

| owner/pipeline | MAY 写 | MUST NOT 写 |
|----------------|--------|----------------|
| Gate/OpenClaw | GATES audit/pending/invalidated/approved receipt（人口令后） | 任一 binder 正文 |
| Binder/OpenClaw | review slice 草稿、绑定骨架、接口骨架 | PERF Numbers、DELTA Rounds、evidence、关闭决定 |
| Claude Code | POC code、测量、PERF Numbers、DELTA Rounds、evidence、COMMITS append | L0/L1/meta、人口令回执 |

1. Control/implementation pack MUST 输出 `allowed_sections`；仅有文件路径权限不足。
2. completion 或 pipeline step 若修改越权 section，MUST 报
   `cross_role_section_write` 并 fail closed。
3. Binder 对完整 contract 可 no-op recheck；不得为“修健康”伪造 Numbers。
4. OpenClaw 生成的性能叙述若无 Claude Code completion + measure/evidence receipt，
   必须标 `unverified`，不得更新 baseline current。

## 拟修改 [[META-012]]

Task Manifest / Context Plan MUST 同时绑定：

```text
bundle_mode | slice_id/path/content_sha | allowed_sections | mutable_sections
```

Context verify MUST 重算 slice SHA；旧 whole-file plan 与 review-slice plan 不兼容，
不得在同 Episode rebind。

## 拟修改 [[META-013]]

1. Gate receipt/event MUST 记录 `bundle_mode` 与 slice manifest SHA。
2. Replay diff MUST 区分 `contract_slice_changed` 与 `mutable_evidence_changed`。
3. 测量结果进入 verified Episode 必须有 Claude Code run/lease/completion 与真实
   measure/evidence receipt；OpenClaw 文档修改不能冒充测量事件。
4. 从 legacy whole-file 迁移到 review-slice 必须创建新 Episode / Manifest。

## 当前主题矫正

对当前仍 exploring 的主题：

1. 审计新增性能数字是否存在真实 Claude Code run/lease/measure/evidence 回执。
2. 无回执：数字保留但标 `unverified`，TOPIC baseline 保持/恢复 stale。
3. 有回执：由 Claude Code 复验，并对齐 TOPIC baseline SHA/status、PERF、DELTA；
   不改写历史 round。
4. 迁移 TOPIC/DESIGN/PERF/DELTA/INTERFACE review slices，追加 bundle-mode
   迁移说明；完成一次新切片重审。

## 实现范围

1. `spec/meta/templates/poc/`：切片标记与 mutable section 模板。
2. `spec/meta/tools/ndf_workflow_status.py`：slice parser、canonical hash、bundle mode、
   精确失效原因与迁移投影。
3. `spec/meta/tools/ndf_context.py` / `ndf_replay.py`：slice manifest、
   `allowed_sections` 与 replay 分类。
4. `.cursor/skills/ndf-workflow-canvas/` + managed Canvas：切片清单、角色越界 blocker、
   legacy/migration 状态。
5. 当前 POC 装订器迁移与越权 evidence 审计。

## 验收标准

1. 修改 TOPIC/DESIGN/绑定/接口切片时只命中规定失效集合。
2. 追加 PERF Numbers、DELTA Rounds、evidence、COMMITS、GATES 时所有 gate SHA 不变。
3. OpenClaw 写 measurement section 的负例报 `cross_role_section_write`。
4. legacy whole-file receipt 不会验证为 review-slice receipt。
5. 无真实测量回执的数字不能把 baseline 标 current。
6. Meta graphcheck hard_errors=0；workflow/context/replay tests 通过；Canvas 快照有效。
