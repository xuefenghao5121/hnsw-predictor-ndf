# Verification configs (`cfg-*`)

命名、可引用的**配置身份**（环境变量 + 图/搜索旋钮）。  
与 `baselines/bl-*` 组合构成黄金三要素中的「配置」腿。

| config_id | 角色 | 文件 |
|-----------|------|------|
| `cfg-sla-ef100` | CON-GOLDEN A / SLA 基线 | [cfg-sla-ef100.md](cfg-sla-ef100.md) |
| `cfg-adaptive-ef90` | CON-GOLDEN B / DEC-086 | [cfg-adaptive-ef90.md](cfg-adaptive-ef90.md) |
| `cfg-m24-ef60` | CON-GOLDEN C / DEC-087 | [cfg-m24-ef60.md](cfg-m24-ef60.md) |

**规则**（[[META-007]]）：改参 = 新 `cfg-*` 或 POC 卡内 experimental 全量 env；
MUST NOT 原地偷改已被 `bl-*` / TOPIC 引用的 cfg 语义而不 bump id。

## 头字段（可选）

| 字段 | 语义 |
|------|------|
| `measure_script` | repo 相对路径的可执行入口（如 `scripts/run_golden.sh`） |
| `measure_binary` | 脚本调用的 benchmark 二进制（repo 相对，可选） |

POC 卡可 inherit cfg 的 Measure，或在 `PERF_BASELINE.md` 头字段 / `## Measure` 中覆盖。
性能线四腿：`trunk_sha` × `config_id` × `measure` × `numbers`（见 [[META-007]]）。
