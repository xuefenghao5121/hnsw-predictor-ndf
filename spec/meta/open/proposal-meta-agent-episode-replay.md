# Process 提案：Git-like Agent Episode Replay

> track: process
> Status: Implemented on 2026-08-12
> 日期: 2026-08-12
> 新增: META-013
> refines: META-012
> 关联: [[META-010]], [[META-011]], [[META-012]]
> 范围: Agent task manifest / episode history / replay object store / event evidence / Canvas Replay

## 1. 背景

[[META-012]] 已把 Agent 执行输入收敛为可验证的 Context Plan / Bundle，并要求
gate、runtime lease 与 completion evidence 绑定当前 git 和 source generation。
但它仍主要回答“这次任务应该看到什么”，尚未完整回答：

1. Agent 当时实际看到了什么、按什么顺序收到哪些工具观测；
2. OpenClaw Control 与 Claude Code Implementation 如何证明来自同一个业务任务；
3. 上下文压缩、会话切换或运行结束后，如何保留不可改写的父历史；
4. 哪些历史可以精确审计，哪些只能用记录值模拟，哪些可以在沙盒复验；
5. 如何避免把重新调用模型得到的新回答冒充历史原样回放。

因此需要在 Context Compiler 之上增加内容寻址的 Agent Episode 层。它管理上下文、
事件、观测、运行态与结果的时间 DAG，但不成为新的产品或 process 条款 SoT。

## 2. 决策

新增 [[META-013]]「Agent Episode、事件链与回放等级」，定义：

```text
Task Manifest
→ role-specific Context Plan / Bundle
→ gate + dispatch pack + runtime lease
→ model/tool/filesystem/git events
→ completion + verification + Close receipts
→ checkpoint / branch / merge / replay
```

Context Plan 是执行输入 IR；Episode 是输入、事件与结果的可审计时间 DAG。二者
MUST NOT 混为一物。

每次可写 Agent 委派 MUST 创建或续接显式 Episode，并记录共同的 Task Manifest。
OpenClaw、Claude Code 与 Canvas 的 role plan MAY 有不同 SHA，但 MUST 引用同一
`manifest_sha`，不得再把一个角色的 plan 冒充另一角色的真实上下文。

## 3. 真实性边界与四级回放

Replay MUST 显式声明等级：

| 等级 | 行为 | 保证 |
|---|---|---|
| R0 Audit | 不执行模型或工具，重建历史对象与事件 | 已存字节、顺序、SHA 精确一致 |
| R1 Observation | 使用已记录 response 与 tool cassette 重建 Agent 所见 | 无外部副作用，记录观测精确 |
| R2 Sandbox Outcome | 在绑定 git/worktree 与沙盒 profile 中重跑允许命令 | 文件/spec SHA 精确；性能按声明容差 |
| R3 Counterfactual Fork | 更换模型、上下文、假设或观测后续写新分支 | 新历史；MUST NOT 宣称复现原决策 |

本流程 MUST NOT 承诺 LLM 逐 token 确定性，也不保存或伪造隐藏
chain-of-thought。平台不可见的 system surface、不可版本化远端状态与未捕获 runtime
stream MUST 标为 coverage gap。重新调用模型属于 R3，不属于 R0/R1。

## 4. Task Manifest 与角色上下文

新增 `ndf-task-manifest/v1`，至少绑定：

```text
intent | topic | task | track | business_goal
binder_roots | clause_seeds | repo_head | baseline | human_gates
shared_graph_closure | conflicts | evidence_refs | role_policies
manifest_sha
```

`ndf_context.py` SHOULD 增加：

```text
manifest-create | role-plan | context-expand | context-verify
```

写任务默认使用 strict 图策略：图闭包截断、gate/context/file drift 或禁止写根重叠
MUST 阻止 dispatch。Canvas 摘要 MAY 将非写任务截断显示为 warning。

Context Compiler 同时补齐结构化 ledger/trailer joins、稳定接口的 `trunk-ref`
joins、promote impact 一跳与 `superseded-by` 重定向。

## 5. 可信证据根

Episode Store 建立前，现有 receipt MUST 先完成语义强化：

1. Close `output_sha` MUST 等于 `evidence_paths` 的 canonical bundle SHA；
2. command MUST 匹配 task/step allowlist；不同验证步骤只能接受对应 verifier 产物；
3. runtime lease MUST 与 pack、manifest、context plan、repo/base SHA、worktree 和
   `allowed_write_root` 完全绑定；
4. `lease-record` MUST 做语义复验，不能只做字段 shape validation；
5. action receipt MUST 使用 `prev_event_sha` 防止删除和重排；
6. gate approval MUST 校验 phrase、审批主体、时间、source ref 与完整 bundle SHA；
7. embedded projection receipt MUST 绑定真实 Canvas payload SHA 与 absorbed action；
8. legacy Close/action/gate/lease 只能导入为 `legacy_unbound` / `legacy_import`，
   MUST NOT 进入 verified Episode commit。

任何不能通过上述验证的 artifact 均不得使 gate、dispatch、Close 或 Replay 状态变绿。

## 6. 内容寻址对象与事件链

新增本地工具 `spec/meta/tools/ndf_replay.py`，默认对象库：

```text
.ndf/replay/
  objects/<sha-prefix>/<sha-rest>
  refs/episodes/ | refs/topics/ | refs/runs/
  refs/branches/ | refs/tags/
  events/<episode-id>.jsonl
  config.json
```

`.ndf/replay/` 默认 gitignored。对象类型：

- Blob：manifest、plan/bundle、pack、receipt、tool cassette、model turn、
  provenance、workspace/git snapshot、redaction map；
- Tree：preflight、turn、completion、checkpoint 的命名对象集合；
- Commit：tree、parent、actor、task/topic/track/repo/context bindings；
- Ref / Branch：可原子更新的 Episode、topic、run 与分支指针；
- Tag：人工 gate、reviewed proposal、里程碑等不可变标记；
- Merge commit：合并多个角色分支的已验证对象与结果，不合并聊天叙述。

所有对象 MUST 使用 canonical JSON SHA。`fsck` MUST 验证对象哈希、tree 引用、
parent DAG、ref/tag、事件链与 redaction lineage。

事件使用 `ndf-replay-event/v1`：

```text
seq | episode_id | timestamp | kind | actor
session_id | run_id | topic | task | track
payload_sha | repo_head | manifest_sha | context_plan_sha
prev_event_sha | event_sha
```

Episode 内事件按 monotonic `seq` 串行并形成哈希链；并发角色使用独立 branch，
最终通过多 parent merge commit 汇合。

## 7. Tool Cassette、Model Provenance 与 Compaction

`ndf-tool-cassette/v1` MUST 保存 Agent 实际看到的规范化调用、stdout/stderr blob SHA、
exit code、cwd/worktree、环境 allowlist 指纹、外部资源版本与 replay policy。

- 本地只读工具 MAY 在 R2 沙盒重跑；
- MCP/远端工具默认 `recorded-only`；
- 写工具仅可在显式隔离沙盒中 live replay；
- secret/env 只保存 allowlisted 字段与存在性指纹，不保存值。

`ndf-model-turn/v1` MUST 绑定 provider/model/API/runtime build、参数、tool schema、
rules/skills、manifest/role plan、可见 prompt surface、输入输出 blob 与 coverage。
不可见平台 surface 只能记版本/指纹或 `unknown_hidden_surface`。

Compaction MUST 创建 `ndf-replay-checkpoint/v1` commit，绑定覆盖事件范围、raw digest、
保留对象、重新编译的 manifest/plan、summary 与 open decisions。原始事件和父历史
MUST NOT 被覆盖。summary 仅用于导航，MUST NOT 单独用于 dispatch、gate 或 Close。

## 8. Agent 捕获与工作流集成

1. `control-pack` 创建或续接 OpenClaw Control branch，记录可获得的 request/response、
   workspace binding、文件差异与 coverage；
2. Claude Code pack 在 manifest/context verify 后创建 Implementation branch；
   start handshake 创建 run ref 与 lease，completion 绑定 changed files、commit、
   reproduce commands 和 evidence；
3. gate tag 只能由已验证的人类 gate receipt 创建，Agent MUST NOT 自行制造 approval tag；
4. post-check 与 isolation 通过后释放 lease并创建 completion commit；
5. promote/close MAY 用 merge commit 连接探索 Episode、reviewed proposal、Trunk commit
   与 verification/golden receipts；
6. 自动记录必须通过显式 `--episode` 或 `NDF_REPLAY_EPISODE` 启用，MUST NOT 隐式记录
   无关会话。

平台仅提供 completion 而非完整 event stream 时，必须记录
`completion_only` / `messages_only` coverage，不得用事后摘要伪装 `full_stream`。

## 9. Privacy、保留与装订

- 原始 replay store MUST 本地加密或由等价受控 artifact store 承载；
- redacted export MUST 生成新 tree/commit 与 `ndf-redaction-map/v1`，不得修改原对象；
- export 默认移除 token、session key、用户标识、SSH/API secret、环境值与 PII；
- gate、manifest、plan 与对象 SHA 保留；
- 大 blob MAY 按 retention policy 冷存，但 commit MUST 保留 SHA、size、location、
  availability 与 redaction status；
- 关闭/晋升时只把小型 replay manifest、tip SHA 与必要 evidence 指针写入
  `REPLAYS.md` 或归档装订器；大型 transcript/blob 不进入产品规范树。

## 10. Canvas Replay

Canvas 新增独立 Replay 视图，至少回答：

1. Agent 当时知道什么；
2. 使用哪个 manifest、role plan 与 gate；
3. 看到了哪些 tool observations；
4. 修改和验证了什么；
5. 哪些 runtime/prompt surface 未捕获；
6. 当前支持哪个 replay level；
7. 两个 run 的上下文、事件与结果差异。

UI MUST 分开呈现 R0/R1/R2/R3。默认入口为 R0 Audit；R2 必须显示 sandbox、
网络、写根、副作用与成本确认。Canvas 仍是派生投影，不成为 Replay SoT。

## 11. 产物

确认后依次落地：

1. `spec/meta/process.md`：新增 [[META-013]]；
2. `AGENTS.md` / `spec/meta/README.md`：增加 META-013 与 Episode 指针；
3. `ndf_workflow_evidence.py` / `ndf_workflow_status.py`：强化 receipt 信任根；
4. `ndf_context.py`：Task Manifest 与 role plan 派生；
5. `ndf_replay.py`：object/event/ref/tag/branch/merge/checkpoint/fsck；
6. tool cassette、model/runtime provenance、redaction/retention；
7. OpenClaw Control 与 Claude Code runtime 捕获，先 completion-only，再按平台能力扩展；
8. R0/R1、R2 sandbox 与显式 R3 fork；
9. Canvas Replay、`REPLAYS.md` ledger 与相关文档；
10. 单元、负例、崩溃恢复与端到端测试。

## 12. 边界

- 不修改产品 `src/`、`include/`、`tests/`、产品 SLA 或现有 POC 实现；
- Cursor/Canvas/replay 工具 MUST NOT 修改 `.openclaw/state.json`；
- 不修改或伪造人类 gate；
- 不改写 git 或历史 Episode；
- 不将 Replay Store 冒充产品/process 条款 SoT；
- 不保存 hidden chain-of-thought；
- 不把模型重调用宣传成 deterministic replay；
- 不用 `packages/ndf-harness/` 反推本地流程 SoT；本地验证后另案蒸馏。

## 13. 验收

1. Task Manifest 能机械派生不同角色 plan，且共同 parent 可验证；
2. verified Episode 的 manifest/plan/gate/lease/receipt joins 完整率为 100%；
3. blob 去重、tree/commit SHA、parent DAG、atomic refs、tag/branch/merge 与 `fsck`
   覆盖正常和破坏负例；
4. 事件断链、重排、缺 blob、错误 command/output/evidence join 均不能通过；
5. R0 哈希重建一致；R1 无副作用；R2 仅在沙盒按协议验证；R3 总是创建新历史；
6. checkpoint 后重新 verify Context，summary-only 不得 dispatch；
7. redacted export 不修改原对象且 secret scan 为零泄漏；
8. OpenClaw / Claude Code 捕获覆盖率真实展示，缺 stream 时显式降级；
9. Canvas 能展示 timeline、branch、commit diff、coverage、checkpoint 与 replay level；
10. `.openclaw/state.json` 无 Cursor/replay 侧改动；
11. `ndf_graphcheck.py --meta` hard_errors=0，Python 测试、Canvas TypeScript 与
    端到端 replay fixture 全部通过。
