# Process 提案：Control 流水线一键派发 OpenClaw

> track: process
> refines: META-011, META-013
> depends-on: META-010, META-011, META-012, META-013
> Status: Implemented on 2026-08-13

## 背景

Canvas 的 `启动门禁流水线` / `启动装订器流水线` 当前只通过
`newComposerChat` 生成 Cursor 桥接任务。若 Cursor 停在提示词展示、未实际执行
`control-pack` 与 `openclaw.chat_send`，按钮虽名为“启动”，OpenClaw 却未收到任务。
这符合 Canvas 不能直接调用 shell/MCP 的平台边界，但不符合用户对“启动流水线”的动作语义。

当前 Control 阶段主要处理：

1. 人工门禁流水线（3 闸）的审计、待审摘要、人口令停顿与回执；
2. POC 相关 NDF 装订器文档和工作流准备（6 面）；
3. 不涉及 POC 产品代码、Trunk `src/include/tests` 或 Claude Code 实现派发。

## 目标

`启动…流水线` MUST 表示 Cursor 桥接任务已将绑定 Control pack 发给 OpenClaw，
而不是仅创建一段待执行提示词。Canvas 仍不直接调用 MCP；它创建的 Cursor 任务
MUST 以 OpenClaw 的可验证接收回执为派发终点。

## 拟修改 [[META-011]]

### 启动动作状态机

```text
requested
→ pack_created
→ context_verified
→ openclaw_sent
→ openclaw_acknowledged
→ waiting_human | running | blocked
→ post_action_sync
```

1. `启动门禁流水线` 与 `启动装订器流水线` MUST 创建或续接显式 Episode，
   生成对应 `control-pack`，校验 Manifest / OpenClaw role plan，并调用
   `openclaw.chat_send`。
2. Cursor 桥接任务 MUST NOT 在 `openclaw.chat_send` 之前结束；MUST NOT 将
   `newComposerChat` 创建成功当作 OpenClaw 已派发。
3. 只有获得 OpenClaw 返回值并记录 `openclaw.request` / `openclaw.response`
   （最低 `messages_only` coverage）后，投影才可显示 `acknowledged`。
4. MCP 不可达、pack/context 无效或 OpenClaw 无回执时 MUST 显示 `blocked`，
   保留 blocker 与“重试派发”入口，不得显示“流水线已启动”。
5. 主按钮为整条流水线的一键派发；分步按钮只在已有活跃 Episode 时 resume
   同一 OpenClaw 会话。无活跃 Episode 时分步按钮 MUST 先完成相同桥接状态机。

### 两套流水线职责

| 流水线 | OpenClaw 任务范围 | 停顿条件 |
|--------|-------------------|----------|
| 人工门禁（3 闸） | gate audit、待审 bundle、pending GATES、回执校验 | 每闸必须等待人口令 |
| 装订器（6 面） | TOPIC / DESIGN / PERF_BASELINE / DELTA / INTERFACE / COMMITS 等 POC NDF 与工作流准备 | 每面完成后复检；不代批门禁 |

两套流水线继续保持独立命名、Episode 绑定与分步事件。它们 MAY 在同一 OpenClaw
长连接会话中执行，但 MUST 使用不同 `pipeline` 与 Episode/step 身份；MUST NOT
将装订器面称作门禁闸。

### 写入边界

OpenClaw 在本阶段 MAY 写：

- `poc/<topic>/ndf/`
- 经既有 process/poc 路由允许的提案草稿
- 项目绑定所需 `.openclaw/state.json`
- gitignored Episode / message / action evidence

MUST NOT 写：

- `src/`、`include/`、`tests/`
- stable `spec/meta/` 正文（本提案确认落地除外）
- 人工未给出口令的 `GATES.md approved_by`
- Claude Code 实现代码或 Trunk 验收结果

## 拟修改 [[META-013]]

1. 一键启动 MUST 将 pack、request、response 与 pipeline step 记录到同一 Episode。
2. `openclaw_sent` 无 response 时只能是未完成派发；恢复时可按相同
   request identity 幂等重试，MUST NOT 生成重复门禁批准。
3. 回放必须能区分：
   - Canvas/Composer 创建任务；
   - Cursor 完成 pack/context；
   - MCP 请求已发出；
   - OpenClaw 已确认；
   - OpenClaw 后续分步修改。

## 实现范围

1. `ndf_workflow_status.py`
   - 增加 Control dispatch receipt / 状态投影；
   - 校验 pipeline、Episode、request/response identity；
   - 输出 `requested|sent|acknowledged|blocked|waiting_human|running`。
2. Canvas
   - 主按钮文案保持“启动”，但 Cursor prompt MUST 明确执行到
     `openclaw.chat_send` 返回并完成消息记录；
   - 展示 `正在派发 / OpenClaw 已接收 / 等待人口令 / 阻塞`；
   - 提供“重试派发”，不得只显示一段可复制提示词。
3. `openclaw-delegate.md` / `actions.md`
   - 将 OpenClaw 回执定义为启动动作终点；
   - 门禁流水线优先；装订器流水线覆盖 POC NDF 与工作流准备；
   - 明确禁止顺带派发 Claude Code。
4. 测试
   - 正例：点击启动后 pack → chat_send → response → receipt → snapshot；
   - 负例：只创建 Composer、MCP 不可达、无 response、context drift；
   - 幂等：同 request 重试不重复批准或重复创建流水线。

## 验收标准

1. 点击任一“启动流水线”后，若 OpenClaw 可达，必须在同一 Cursor 任务中看到
   OpenClaw 返回摘要，而非仅看到桥接提示词。
2. OpenClaw 未收到时，Canvas 必须显示 blocked/未派发。
3. 门禁流水线在 OpenClaw 接收后停在准确的人口令；装订器流水线继续完成 POC NDF/
   工作流准备并复检。
4. R0 能重建 pack、request、response 与后续 gate/binder step；无回执不能宣称启动成功。
