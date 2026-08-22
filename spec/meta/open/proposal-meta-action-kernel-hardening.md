# Process 提案：Commander Action Kernel 与派发闭环加固

> track: process
> Status: Implemented on 2026-08-20
> control-flow: managed
> proposal-id: meta-action-kernel-hardening
> flow-id: meta-action-kernel-hardening
> 日期: 2026-08-20
> 修改: META-011 / META-012 / META-013（薄补丁）；action-registry；ndf_actions；ndf_workflow_status；ndf_dispatch_send；ndf_replay；ndf_workflow_evidence；cockpit UI；hooks；tests；AGENTS/README
> depends-on: META-011, META-012, META-013, META-014
> 范围: typed ActionSpec；workspace identity≠execution HEAD；Episode 贯通；capability preflight；事务 closeout；projection fail-closed；防复发测试
> land-targets: spec/meta/process.md, spec/meta/cockpit/action-registry.json, spec/meta/cockpit/src/ActionButton.tsx, spec/meta/tools/ndf_actions.py, spec/meta/tools/ndf_workflow_status.py, spec/meta/tools/ndf_dispatch_send.py, spec/meta/tools/ndf_replay.py, spec/meta/tools/ndf_workflow_evidence.py, .cursor/hooks/ndf-dispatch-after-pack.sh, AGENTS.md, spec/meta/tools/README.md

## 1. 背景

反面路径（hotspot `poc_measurement`，2026-08-20）：

1. 可写 Composer prompt 未传播 `--episode`；pack 一旦因其他原因变可写即触碰
   「writable pack requires explicit Replay Episode」。
2. commit 后 `.openclaw/state.json` 的 `repo_head`/`bound_sha` 落后于 HEAD，被当成
   `workspace_unbound`；身份与执行绑定混为一谈。
3. `safe_to_dispatch` 只证明静态规则 + transport 可达，不证明 worktree / 写权限 /
   命令批准 / sudo·cgroup 能力。
4. afterShell hook 用「最新 started action」关联 pack，可错配。
5. Replay 目录内嵌完整 prompt 超预算 → post-action snapshot 失败，旧投影仍可点。
6. stale projection 仍启用可写 repair；缺失 `enabledActions` 时 UI 默认启用。

根因：`action-registry.json` 不是完整执行 SoT；语义分散在 prompt 分支、
`DELEGATE_*`、pack CLI、hook 字符串匹配与 closeout。

## 2. 决策

1. **ActionSpec。** registry 升为可校验 v2 字段（兼容读取 v1）：`provider`、
   `episodePolicy`、`requireFresh`、`packKind`/`packTask`、`requiredCapabilities`、
   `attemptBinding`。`ndf_actions` 从 registry 编译 prompt/enablement；可写动作
   MUST 在 `action-begin` 与 pack CLI 写入同一 `--episode`。
2. **Workspace identity ≠ execution HEAD。** `workspace_bound` 只比
   `repo_root` + `active_topic`（及必要指纹）；HEAD 漂移记
   `execution_binding_stale`，pack 以 live `git_head()` 为 `base_sha`，
   MUST NOT 仅因 commit 前进而判身份失绑。
3. **Capability readiness。** 拆分
   `static_preflight_passed | transport_reachable | execution_capabilities_ready | lease_acquired`；
   测量类声明 `sudo_cgroup` / `write_poc_ndf` / `run_sustained`；缺能力时
   `waiting_human` 或 fail-closed，不得先送再碰运气。
4. **Attempt 关联。** pack / worker message MUST 携带
   `action_id + catalog_action_id + episode_id + attempt_id`；hook MUST 按这些字段
   匹配，MUST NOT 取全局最新 started。
5. **Closeout 事务。** transport / worker completion / commit / projection 分账；
   失败 completion 也 MUST Episode-bind；snapshot 失败 →
   `succeeded_projection_stale` 或 fail closeout，不得冒充全成功。
6. **Projection fail-closed。** Replay 目录裁剪且不内嵌全文 prompt；超预算省略
   bucket 而非整份失败；writable+`requireFresh` 在 stale 时 disable；
   `ActionButton` 缺 enabled 条目默认 disabled；failed/cancelled 终态可被吸收为
   projection `fresh`。
7. **死路清理。** 退役 guest-replay 按钮（CLI-only）；对齐 measurement 写集
   （PERF/DELTA/evidence/COMMITS）；纠正 lease / land-review / genesis 契约漂移。

不新增 `META-*` 数字号；在 [[META-011]]…[[META-013]] 追加短 must 句。

## 3. 落地清单

| 路径 | 变更 |
|------|------|
| `action-registry.json` | v2 字段；measurement 写集；guest-replay 退役；requireFresh |
| `ndf_actions.py` | Episode 贯通；provider 编译；freshness；prompt by attempt |
| `ndf_workflow_evidence.py` | identity vs execution HEAD |
| `ndf_workflow_status.py` | pack readiness；freshness 吸收失败；snapshot 有界 |
| `ndf_dispatch_send.py` | live truth；episode；capability；closeout 事务 |
| `ndf_replay.py` | 目录裁剪实际生效 |
| `ActionButton.tsx` | 缺 enabled → disabled |
| `ndf-dispatch-after-pack.sh` | 按 pack 身份关联 action |
| tests / README / AGENTS / process.md | 对齐 + 回归 |

## 4. 验收

- 可写 prompt 含同一 `--episode`；无 Episode 不可 `safe_to_dispatch`
- commit 后 identity 仍 bound；pack base_sha = live HEAD
- hook 不错配 action；snapshot 超预算仍可发布 core
- stale / 缺 enabledActions 时不可执行可写 CTA
- transport≠success；capability 缺失 fail-closed；graphcheck --meta hard_errors=0
