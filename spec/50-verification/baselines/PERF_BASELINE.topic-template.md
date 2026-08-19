# Perf baseline — \<topic\> (template)

> trunk_sha: \<short or full；R0 后 MUST；绑定阶段可暂缺并在 Notes 说明\>  
> config_id: cfg-sla-ef100  
> protocol: [[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]]  
> status: current  
> vs: bl-trunk-golden-\<shortsha\>  
> measure_script: scripts/run_golden.sh  
> measure_binary: \<optional\>  
> verifies: VER-043   # 可选薄指针

复制到 `poc/<topic>/ndf/PERF_BASELINE.md`。收到 **`DESIGN已审核`** 后 MUST 先写**绑定头**
（`vs` × `config_id` × `measure_script`），TOPIC 头加：

```text
> perf_baseline: ndf/PERF_BASELINE.md
```

**唯一绑定**：同主题一套对照金标；改绑 MUST 改头字段并在 `DELTA.md` 记一笔（[[META-007]]）。  
对齐现行金标索引：`spec/50-verification/golden-baseline.md`。

## Config

- 指针：`spec/50-verification/configs/<config_id>.md`（每个 id MUST 可解析）
- 若 experimental：头写 `config_id: experimental`，在此贴**完整** env 表（禁止「见 NOTES」）；
  仍 MUST 钉死 `vs:` 与 `measure_script`

## Numbers

二选一（绑定阶段可写 `pending R0`）：

1. **沿用金标**：写明「沿用 `baselines/<vs>.md` §… / config_id=…」，并链到该文件  
2. **本主题 R0**：cgroup × threads × agg/steady/recall 表（比 Δ% 的唯一数字源）

## Measure

可执行入口（Agent 复现必读）。二选一：

1. **inherit cfg**：写明 `inherit cfg-<id>` 并链到
   `spec/50-verification/configs/<config_id>.md` 的 `measure_script` / `measure_binary`
2. **显式路径**：repo 根相对（如 `scripts/run_golden.sh`）或 topic 相对（如 `run_r0.sh`）

头字段 `measure_script` / `measure_binary` 覆盖 cfg 时以卡为准。

## Notes

测量瑕疵 / 绑定阶段拟对照金标 trunk / sha 与金标不一致时的说明。不得另藏一套「真基线」。
