# Process 提案：Control 双流水线职责与关闭决策纠偏

> track: process
> refines: META-011, META-013
> depends-on: META-010, META-011, META-012, META-013
> Status: Implemented on 2026-08-13

## 背景

现行 Control 已把人工门禁（3 闸）与装订器修订（6 面）分成两条流水线，但实际
`gate_pipeline` Episode 曾在下一闸被 binder 缺口阻塞时直接创建 `DESIGN.md`、
`DELTA.md`、`INTERFACE.md`。这使 gate 流水线越过职责边界，令独立
`binder_pipeline` 看似多余，也破坏按 `pipeline + step` 回放的语义。

同一回合还把历史 R0 负结果散文解释为当前关闭决定：三闸完成后直接建议 reject/close。
然而门禁批准只说明绑定内容获人工确认，不等于用户已决定实现、继续探索或关闭。
当 lifecycle 仍为 `exploring`，且后续出现新前提或潜在价值时，历史关闭建议只能作为
evidence，不能替代当前人工决策。

## 目标

1. 保留两条流水线并强制单一职责：
   - Gate 真值：`GATES.md`、canonical bundle SHA、人口令；
   - Binder 真值：TOPIC / DESIGN / PERF_BASELINE / DELTA / INTERFACE / COMMITS。
2. 允许两条流水线结构化交接，而不是由 gate 顺手完成 binder 工作。
3. 将「三闸通过」与「POC 关闭决定」分开；关闭必须依据当前 lifecycle、最新绑定证据、
   显式人工选择及既有 proposal/DEC 纪律。
4. 保留历史负结果，不因新方向继续探索而改写旧 round。

## 拟修改 [[META-011]]

### 流水线写入所有权

| pipeline | MAY 写 | MUST NOT 写 |
|----------|--------|----------------|
| `gate` | `GATES.md` 的 audit / pending / invalidated 回执与门禁说明 | TOPIC、DESIGN、PERF_BASELINE、DELTA、INTERFACE、COMMITS 正文 |
| `binder` | 当前 facet 对应装订器文件/字段；已有完整 facet 可 audit + no-op recheck | `approved_by`、`gate.confirmed`、关闭决定 |

1. `gate_pipeline` 遇到下一闸 bundle 缺文件或缺字段时 MUST 停止并输出：

   ```text
   blocked_by_binder | next_binder_facet | blocked_gate
   ```

   Canvas MUST 提供指向对应 binder 面的动作；gate Agent MUST NOT 代写缺失 facet。
2. `binder_pipeline` 完成一面后 MUST 复检；若文件已完整，MAY 记录 no-op
   `binder.audit → binder.recheck`，不得为证明流水线存在而重写内容。
3. Gate pack 的精确写入面 MUST 限定为该 topic 的 `GATES.md`（以及 gitignored
   gate receipt/event）；binder pack MUST 按 focus facet 限定文件面。
4. completion 声明若含跨 pipeline 文件 mutation，MUST fail closed 并报告
   `cross_pipeline_write`，不得投影为已完成。

### 交错编排

两条流水线独立保留，但业务顺序是结构化交错：

```text
binder.TOPIC → gate.topic_review
→ binder.DESIGN → gate.design_review
→ binder.PERF_BASELINE/DELTA/INTERFACE → gate.implementation_approval
→ human decision → implementation / continue / close
→ binder.COMMITS append
```

`COMMITS.md` MAY 在实现前创建 ledger 骨架；实际代码/验证 commit 仍在产生后追加。

### 决策与关闭资格

1. 三闸全部有效只产生 `decision_required`；MUST NOT 自动产生 reject/promote/close。
2. 下一决策 MUST 由 Human 显式选择：

   ```text
   implement | continue_exploring | amend | promote | partial | reject
   ```

3. `close_eligible` MUST 由结构化当前事实推导：lifecycle、显式选择、适用的 proposal/DEC、
   close-plan 与验证回执。DESIGN/GATES/NOTES 中的「建议关闭」「负结果」自由文本
   MUST NOT 单独令其为 true。
4. lifecycle 为 `exploring|blocked` 且历史负结果之后出现新假设/新前提时，
   投影 MUST 为 `decision_required` 或 `continue_exploring`，保留旧 round；
   仅已 `rejected|promoted` 的主题适用 [[BEH-025]] 平级新 topic 规则。
5. 用户选择继续同一假设/协议时 MAY amend 当前 topic；实质修改门禁 bundle 后，
   MUST 按 [[META-010]] 追加 `invalidated` 并重新审核受影响闸，不得改写旧回执。

## 拟修改 [[META-013]]

1. Gate→Binder 交接 MUST 记录结构化 handoff 事件，至少绑定：

   ```text
   pipeline | blocked_gate | next_binder_facet | manifest_sha | context_plan_sha
   ```

2. Gate Episode 的 completion MUST 校验其 filesystem mutation 仅落在 gate 写入面；
   Binder Episode 同理校验 focused facet，跨面修改必须显式列出并由 pack 授权。
3. `gate.confirmed` 与 `decision.selected` 是不同事件；前者 actor=human 不推出后者。
4. 历史结论与当前决策 MUST 可分别回放，不得将散文中的 reject 建议合成为
   `decision.selected(mode=reject)`。

## 当前主题矫正

对仍为 `exploring` 的现行主题：

1. R0 负结果保留在 DELTA/NOTES 的历史 round，不改写；
2. 在 TOPIC/DESIGN 登记当前 `active_hypothesis` 与 `open_decision`；
3. 把 GATES 中命令式「下一步 reject/close」改为非决策历史说明；
4. 对受实质修改影响的 gate bundle 追加 invalidated 回执，并重新走相应人口令；
5. 不创建 reject DEC、不归档，除非用户之后显式选择 reject。

## 实现范围

1. `spec/meta/process.md`：补强 [[META-011]] / [[META-013]]。
2. `spec/meta/tools/ndf_workflow_status.py`：
   - 输出 `blocked_by_binder`、`next_binder_facet`、`decision_required`、
     `close_eligible`；
   - gate/binder 精确写入面；
   - 关闭投影不读自由文本作决定。
3. `.cursor/skills/ndf-workflow-canvas/` 与 managed Canvas：
   - 明确 handoff、no-op binder 与关闭决策；
   - gate prompt 禁止创建 binder facet。
4. tests：
   - gate 不得创建 binder 文件；
   - binder 不得批准 gate；
   - 三闸全绿不自动 close；
   - exploring + 历史负结果 + 新假设保持待决策/继续探索；
   - 仅显式选择与关闭证据进入 close。

## 验收标准

1. Gate 被缺失 DESIGN 阻塞时只返回 binder handoff，不创建 DESIGN。
2. Binder 已完整时可 no-op 完成，不破坏已审核 SHA。
3. Gate 全绿后 Canvas 展示人工决策，不默认展示 reject 为下一必做动作。
4. `cross_pipeline_write` 负例 fail closed 且可回放。
5. Meta graphcheck hard_errors=0；workflow/context/replay tests 通过；Canvas 快照验证有效。
