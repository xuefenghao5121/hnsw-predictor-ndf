# Process 提案：Control 双流水线（3 门禁闸 vs 6 装订器面）

> track: process
> refines: META-011, META-013
> depends-on: META-010, META-011, META-013
> Status: Implemented on 2026-08-13

## 背景

Canvas Routed repair 将人工门禁审计与装订器修订扁平成同质按钮，易混称「闸」，且每点一步都重新 Cursor→OpenClaw 全量派发。需要硬分两套流水线，并允许各自同 Episode 续聊、分步回放。

## 变更摘要

1. **[[META-011]]**：Control 任务增加 `gate_pipeline` / `binder_pipeline`；命名纪律——仅人工门禁称「闸」，装订器称「面」；Canvas 分区两主按钮 + 分步 resume。
2. **[[META-013]]**：分流水线分步事件（`gate.audit|draft|confirmed` ×3；`binder.audit|amend|recheck` ×面）；禁止跨流水线合成一条 completion；每条流水线专用 Episode（或同 Episode 必带 `pipeline` + step id）。
3. **工具 / Canvas / skill**：`ndf_workflow_status.py`、`ndf_replay.py`、驾驶舱 Routed repair、`openclaw-delegate.md`。

## 命名与数量

| 流水线 | 叫法 | 步数 | 顺序 |
|--------|------|------|------|
| A 人工门禁 | 闸 / gate | 3 | TOPIC已审核 → DESIGN已审核 → 可以开始实现 |
| B 装订器修订 | 面 / binder facet | 6 | TOPIC → DESIGN → PERF_BASELINE → DELTA → INTERFACE → COMMITS |

## 会话模型

- 整条流水线 **一次** Cursor 派发；分步按钮 = resume 本流水线 Episode。
- A：每闸必停人口令；MUST NOT 代批。
- B：默认无口令；写完复检 topic-health。
- A 与 B **不得**混成一个无标签超级派发；投影可提示 B 挡住 A 的下一闸。

## 回放事件

```text
gate.audit → gate.draft → gate.confirmed   # per gate id
binder.audit → binder.amend → binder.recheck  # per binder facet
```

禁止将 3+6 合成一句「Control 已处理」。
