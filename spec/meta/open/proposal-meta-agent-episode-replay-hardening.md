# Process 提案：Agent Episode Replay 可信性加固

> track: process
> Status: Implemented on 2026-08-13
> 日期: 2026-08-13
> 修改: META-012, META-013
> depends-on: META-010, META-011, META-012, META-013
> 前序: `spec/meta/open/proposal-meta-agent-episode-replay.md`
> 范围: historical audit / manifest derivation / event state machine / dispatch binding / R2 / redaction / Canvas acceptance

## 1. 背景

`proposal-meta-agent-episode-replay.md` 已建立 Task Manifest、内容寻址 Episode、事件链、
四级 Replay 与 Canvas Replay 的主体结构。2026-08-13 深度审计确认：功能广度已形成，
但若按 [[META-012]]、[[META-013]] 的“可写委派必须绑定、历史必须可精确审计、
false-green rate=0”目标验收，仍存在系统性缺口：

1. strict R0 使用当前 checkout 与活体 worktree 复验旧 Episode，仓库推进或 worktree
   清理后会把合法历史判坏；
2. merged Episode 的 reconstruct 未完整遍历 parent DAG，可遗漏 Control /
   Implementation 分支却仍显示 audit green；
3. Manifest 可在篡改图闭包、budget、blocker 后重新计算 SHA，现有验证未证明其来自
   Context Compiler 的确定性派生；
4. writable pack 可不带 Episode，主 POC pack 的 manifest binding 不完整；
5. fsck、事件 actor/payload/order、completion mutation、verifier receipt 与 action
   projection 仍有 false-green 路径；
6. share-safe export 对 `--token <value>` 等相邻参数语义的 secret 扫描不足；
7. R2 尚未在当前宿主完成真实执行，且未校验环境指纹与多角色 plan 选择；
8. Canvas Replay 页面虽已实现，但当前无真实 Episode，R0/R1 通过 Composer 模型间接
   执行，R2 未展示 evidence-specific profile，diff 也未按语义面分类；
9. 当前实现仍在未提交工作树中，尚无稳定 Git 时间锚点。

因此本轮不是新增另一套 Replay，而是对前序实现做可信性加固，使“存储完整”、
“历史有效”、“当前可恢复”和“可执行重放”成为彼此独立、可验证的结论。

## 2. 决策

本提案确认以下原则：

1. [[META-013]] 的 R0 MUST 只依赖内容寻址历史及其记录证明；MUST NOT 因当前 HEAD、
   当前 gate 或已清理 worktree 漂移而把历史对象判坏。
2. “历史审计”与“当前恢复/重新派发 readiness” MUST 输出不同结果：

```text
historical_integrity | historical_semantics
current_restore_ready | current_dispatch_ready
```

3. verified Episode MUST 证明完整 parent DAG、Manifest 编译派生、role/task 权限、
   gate→dispatch→lease→completion→release/verification 的合法状态迁移。
4. 任一可写 pack 缺 Episode、manifest、role plan 或 exact allowed root 时 MUST
   fail closed，不得降级为未记录派发。
5. Canvas R0/R1 MUST 不经模型执行；若平台只能打开 Composer，则动作 MUST 标为
   “生成操作指令”，不得显示为已执行 Replay。

## 3. Historical R0 与完整 DAG

### 3.1 两类验证器

将 Context/lease 验证拆分为：

- `verify_*_recorded`：验证 canonical SHA、编译器证明、记录快照、binding proof 与
  commit/tree/event DAG；不读取当前工作树；
- `verify_*_current`：用于 checkpoint 恢复、R2 与再次派发，显式检查当前 HEAD、文件、
  gate、worktree 与 environment drift。

`audit --strict` 的 R0 默认使用 recorded 验证；另提供 current-restore 状态，不得混淆。

### 3.2 完整 parent DAG 重建

`reconstruct()` MUST 遍历目标 commit 的所有 parent，并：

1. 以 commit DAG 拓扑序重建所有分支 tree；
2. 对重复对象去重，但不得丢弃 branch provenance；
3. 明确输出 branch-local event order 与 merge parent；
4. 若任一祖先 tree/event/payload 不可达或缺失，R0 MUST fail；
5. 禁止只遍历目标 commit tree 后宣称 Episode 已精确重建。

### 3.3 fsck 类型与 DAG 约束

`fsck` MUST 验证：

- commit `tree` 必须指向 tree，parent 必须指向 commit；
- refs/episode/branch/run/tag 必须指向其允许的对象类型；
- commit parent DAG 无环；
- event-chain tree 的命名、payload 与 branch 元数据一致；
- redaction lineage 的 source/export/map 类型与闭包合法。

## 4. Manifest 编译派生与角色权限

Task Manifest MUST 增加 compiler derivation proof，至少绑定：

```text
compiler_id | compiler_sha | compiler_policy
seed inputs | graph source digest | binder/evidence input digest
derived closure/blockers/truncation/conflicts/baseline digest
```

`verify_manifest` MUST 以相同 compiler policy 重派生 Manifest 语义，不能只校验调用者
提供内容的自签 SHA。写任务中任何 closure、blocker、budget、baseline 或 role policy
不一致 MUST 阻断。

Role Plan MUST 校验 `role × task × track` 兼容矩阵：

- OpenClaw：Control 文档流；
- Claude Code：Implementation/Test 及明确批准的集成面；
- Canvas：只读投影与操作编排。

角色不兼容不得仅靠 allowed roots 偶然为空来防护。

## 5. 可写委派、lease 与 completion

### 5.1 Episode 强制绑定

所有 writable `pack` / `genesis-pack` / repair pack MUST：

1. 要求显式 Episode；
2. 保存并返回 `manifest_sha`、role `plan_sha`、pack object SHA；
3. dispatch event 必须绑定同一组 SHA；
4. 缺任一绑定时 `safe_to_dispatch=false`；
5. `bind_pack_to_episode()` MUST NOT 对 writable pack 静默 no-op。

### 5.2 Durable lease proof

lease acquisition 在 live worktree 验证成功后 MUST 写入
`ndf-runtime-worktree-proof/v1`，包含 acquisition-time HEAD、branch、base、repo root、
allowed root、run/session 与 proof SHA。历史 audit 使用 recorded proof；当前恢复另做
live validation。

release MUST 承接历史 active binding，不得因 Trunk 后续推进而重新编译成另一份 plan。

### 5.3 完整 mutation 证明

completion MUST 比较 acquisition snapshot 与 completion snapshot，至少覆盖：

- `git status --porcelain=v2`；
- tracked diff；
- untracked files；
- allowed root 外 mutation；
- declared `changed_files` 与实际 mutation 的双向集合相等。

只验证 Agent 自报路径不足以通过 completion。

### 5.4 Verifier 可信来源

Close/post-check receipt MUST 绑定注册 verifier 的绝对路径、argv、版本 SHA、真实退出码与
结构化输出 schema。任意字节文件 + 自报 `passed` 不得使 Close 或 completion 变绿。

## 6. 事件语义状态机与 projection

为关键事件定义 actor、schema、前置状态与后继状态：

```text
manifest.created
→ context.compiled
→ context.verified
→ gate/proposal confirmed
→ dispatch.preflight
→ lease.acquired
→ model/tool/filesystem/git events
→ completion
→ lease.released
→ verification/close
→ checkpoint/merge
```

要求：

1. actor 必须匹配事件类型；human gate 不接受 Agent actor；
2. payload identity 必须与 event metadata 完整一致；
3. branch-local 顺序与跨分支 merge 条件必须可验证；
4. `record` 通用入口产生的未验证事件只能进入 unverified branch；
5. malformed action JSONL 不得静默丢弃后得到 green；
6. projection freshness 必须使用 [[META-011]] 的
   `fresh|refresh_in_progress|stale_after_action|unknown` 语义，并证明最新终态 action
   已被 snapshot 吸收；
7. snapshot update 与 verify 都必须生成可审计 `snapshot.embedded` 事件（显式 Episode
   启用时）。

## 7. R1、R2 与 checkpoint

### R1

R1 MUST：

- 只展示完整 recorded model/tool observations；
- 验证每个 observation 的 replay policy；
- 明确缺失 surface，不得与 R0 仅更换 label。

### R2

R2 MUST：

1. 选择与目标 run/role/manifest 精确匹配的 role plan，禁止从 DAG 中取“第一个” plan；
2. 校验 cassette 的 environment allowlist fingerprint、cwd、tool/runtime version；
3. 覆盖 exact output、epsilon、write violation、context/gate drift 负例；
4. evidence-specific profile 明确显示 adapter、network、commands、write roots、成本、
   副作用与 expected outputs；
5. 本宿主不能运行 `bwrap` 时，验收状态 MUST 为 `environment_blocked`，不得算 R2 passed；
6. MAY 增加等价隔离 adapter，但 MUST 有独立威胁模型和真实执行测试。

### Checkpoint

checkpoint MUST 覆盖完整 merged DAG，而非单一 branch JSONL；retained refs MUST 足以恢复
Manifest、Plan、gate、observations 与 open decisions。恢复命令 MUST 重新执行 current
readiness，并证明 summary-only 不能 dispatch。

## 8. Redaction 与保留

share-safe export MUST：

1. 使用结构化参数语义识别 `--token value`、header、URL credential、env assignment；
2. 对完整导出闭包运行 secret/PII scanner；
3. scanner 非零时拒绝生成 share-safe ref；
4. fsck 验证 redaction map 覆盖和导出闭包不可达原 secret parent；
5. 增加相邻 argv、编码文本、嵌套对象与分片 secret 负例。

Retention 仍可先保持 non-destructive plan；若实际 cold-store，后续 MUST 增加 location、
availability、receipt 与 retrieval verification。

## 9. Canvas Replay 验收

Canvas MUST：

1. 展示实际 Manifest 摘要、ordered context、visible prompt surface、gate、verification，
   不只显示 SHA/count；
2. 将 coverage/join/semantic/current-drift 分类显示；
3. diff 按 manifest/context/events/observations/results/verification 分面；
4. R0/R1 使用无需模型的本地只读执行通道；无法执行时按钮名称与状态必须明确为
   “Open instructions”，不得宣称 replay completed；
5. R2 在确认前展示具体 profile，而不是一个全局 checkbox；
6. checkpoint 展示覆盖 branch/seq 与重新验证结果；
7. 以真实 Episode 驱动页面验收，空 store 仅算 empty-state UI。

## 10. 测试与验收

新增或强化以下负例：

1. repo HEAD 推进、gate 漂移、worktree 删除后，historical R0 仍通过，current readiness
   明确失败；
2. merge 后再追加 main commit，R0 仍能看到所有 parent branch 事件；
3. Manifest closure/blocker/budget 被篡改并重签仍失败；
4. writable pack 无 Episode/manifest/plan 时 fail closed；
5. 未申报 mutation、越界 mutation、伪 verifier output 失败；
6. malformed action、错误 actor、非法事件顺序失败；
7. commit tree 指 blob、parent 指非 commit、ref 指错类型、parent cycle 失败；
8. argv 相邻 secret、嵌套/编码 secret 的 export 失败；
9. R2 environment mismatch、wrong role plan、epsilon mismatch、write violation、gate drift
   失败；
10. checkpoint 完整恢复与 summary-only dispatch 失败；
11. Canvas snapshot drift 检出，Replay 页面使用真实 Episode fixture；
12. concurrent commit CAS 与多 ref crash recovery。

最终验收：

```text
false_green_rate = 0
historical_R0_after_repo_advance = pass
historical_R0_after_worktree_cleanup = pass
merged_DAG_reconstruction = 100%
verified_writable_dispatch_without_episode = 0
share_safe_secret_scan_findings = 0
live_R2 = pass | environment_blocked（不得记 passed）
Canvas_real_episode_questions = 7/7
```

并运行：

```bash
python3 -m unittest discover -s spec/meta/tools -p 'test_ndf_*.py'
python3 spec/meta/tools/ndf_replay.py fsck
python3 spec/meta/tools/ndf_index.py validate --meta
python3 spec/meta/tools/ndf_graphcheck.py --meta
npx --yes --package typescript@latest tsc --project \
  /home/huawei/.cursor/projects/home-huawei-hnsw-predictor-ndf/canvases/tsconfig.json \
  --noEmit --pretty false
```

## 11. 实施顺序

1. recorded/current 验证拆分 + durable lease proof；
2. Manifest compiler derivation + role/task compatibility；
3. writable pack Episode 强制绑定 + mutation/verifier proof；
4. full DAG reconstruct + typed fsck + transactional CAS；
5. 完整事件语义状态机 + projection absorption；
6. R1/R2/checkpoint 语义加固；
7. structured redaction + export scanner；
8. Canvas evidence/diff/action/profile 改造；
9. 真实 Episode fixture、HEAD 推进/worktree cleanup/R2/Canvas 验收；
10. 将 Replay 相关变更与无关 POC 修改分离，形成稳定 Git commit。

## 12. 边界

- 不修改产品 `src/`、`include/`、`tests/` 或产品 SLA；
- 不修改 `.openclaw/state.json`；
- 不使用 `packages/ndf-harness/` 反推本地流程；
- 不伪造真实 OpenClaw/Claude stream；
- 不因宿主不支持 R2 而降低隔离要求；
- 本提案未确认前，不修改 [[META-012]]/[[META-013]] 正文或 Replay 实现。
