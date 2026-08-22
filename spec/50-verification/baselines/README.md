# Verification baselines (`bl-*`)

命名、可引用的**观测性能线**（`trunk_sha` × `config_id(s)` × numbers）。

| baseline_id | trunk | status | 文件 |
|-------------|-------|--------|------|
| `bl-trunk-golden-434c6f5` | 434c6f5 | current | [bl-trunk-golden-434c6f5.md](bl-trunk-golden-434c6f5.md) |

索引入口：[../golden-baseline.md](../golden-baseline.md)。  
POC 主题卡：`poc/<topic>/ndf/PERF_BASELINE.md`（[[BEH-025]] / [[META-007]]）。

**规则**：promote 后新测 MUST 新 `bl-trunk-golden-<shortsha>`（或明确 bump id）；
MUST NOT 原地改已被 TOPIC `vs:` 引用的卡数字而不改 id。
