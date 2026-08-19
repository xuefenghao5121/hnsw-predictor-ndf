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

- 三道门禁回执仍以 `ndf/GATES.md` 为准；本 hop **不**新写口令、**不**改 GATES。
- **2026-08-19 `poc_prepare_baseline`**：已把 Trunk 对照代码字节级拷进
  `poc/hotspot-optimization/src/`（`disk_hnsw.cpp` / `disk_hnsw.h` / `simd*.h`），
  并加 topic Makefile + `run_r0.sh` 以形成可测 R0 工作区。
  **未改** `pqDistance`（无 D1 SIMD gather）。**未写** PERF Numbers / DELTA Rounds。
- 拷贝对照 `baseline_trunk_sha` `a14339234133cc6c5a2348464954f744c6465efb`（与当前 HEAD 这些路径字节相同）。
- 默认 `run_r0.sh` 只 build + `scripts/run_sustained.sh --config cfg-m24-ef60 --dry-run`。
  实测 Numbers 留给 `poc_measurement`。
- 下一步仍是人工**本轮决策**（`selected_decision`）后再 Delegate POC 做 D1；本 hop 不是实现委派。
