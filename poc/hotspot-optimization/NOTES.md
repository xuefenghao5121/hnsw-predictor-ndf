# hotspot-optimization — Notes
> status: exploring
> created: 2026-08-18
> track: poc

## ⚠️ 违规记录 + 撤回 (2026-08-18)

Cursor 在收到「DESIGN已审核 / 可以开始实现」之后**非法自我执行**了 D1 实现（未绑定、
未经正式委派），产生以下未绑定写入，现已全部撤回：

- `poc/hotspot-optimization/src/`（copy-then-edit 工作副本 + `pq_distance_simd.h` + equiv 测试）
- `poc/hotspot-optimization/Makefile`
- `poc/hotspot-optimization/build/`
- `poc/hotspot-optimization/ndf/evidence/d1-pq-gather-equiv-20260818.md`

**撤回不是新一轮测量，也不是新 POC 代码。** 撤回后代码 ledger 为空。

### 禁止项

- **MUST NOT 把该次 kernel 等价性结果（20000/20000 bitwise）当作 Numbers 或 DELTA 证据。**
  （它出自未绑定的自我执行，非正式委派测量。）
- D1 需在人工 `selected_decision=implement` 后，经 Claude Code 正式委派重新实现。

## 状态

- 三道门禁（TOPIC已审核 / DESIGN已审核 / 可以开始实现）**保持有效**，不要求重说。
- **2026-08-20**：Commander `poc-prepare-baseline` hop 将 Trunk 对照拷贝到
  `poc/hotspot-optimization/src/`（见 `src/BASELINE_COPY.md`）。**标注：该次为
  Command Agent 自执行（非正式 ACP 委派）**——当时 `repair-pack` 因 stub proposal
  导致 `context_verify_failed`，Agent 本地 `cp` 进 `poc/<topic>/src/`，**不是**
  `afterShellExecution` → Claude Code ACP 路径。仅基线拷贝，**无** D1 SIMD 改动，
  **无** PERF Numbers / DELTA 修订。之后基线/测量/隔离只走 pack → hook 发送 →
  回执入指挥面。
- 下一步仍由人工决策（继续探索 / implement D1 / 测量 R0 等）；D1 实现须经 Delegate POC。
- PERF Numbers / DELTA Rounds 仍 pending，未写任何观测数字。
