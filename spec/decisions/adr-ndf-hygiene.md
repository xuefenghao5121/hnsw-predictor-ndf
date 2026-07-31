# ADR: NDF 规范防腐化与双轨 SLA {#DEC-HYGIENE-001}

> 日期: 2026-07-31
> 状态: Accepted
> 关联提案: `spec/open/proposal-ndf-hygiene.md`
> 场景: 场景3（项目重构）

## Context

`spec/` 在快速迭代（P2、冷 I/O、O_DIRECT 诚实基准）后出现结构性腐化：条款 ID 撞车、幽灵决策 `DEC-039`、`OBS-*`/`INTENT-*` 死链、Charter 无模式 QPS 与 Honest 实测冲突、`open/` 堆积已落地文件。若继续在腐化图上叠加条款，精化链与验证覆盖将不可审计。

## Decision

1. **先图后语义**：优先消除重复 ID、物化 `DEC-039`、重写 `ndf.yaml` 前缀、重定向死链，再调和 SLA 与归档。
2. **SLA 双轨（不静默删旧数字）**：
   - **Buffered**（`FINE_BUFFERED=1`）：保留既有 QPS/Recall/RSS 阈值（Charter / CON-SLA-008…010）。
   - **Honest / O_DIRECT**（`FINE_DIRECT=1`）：新增 `CON-SLA-011` 与 Charter `CHR-006` Honest 行，下限取自 2026-07-31 实测（SIFT1M 1T≥100 / 4T≥400，留安全余量相对 130/502）。
3. **Recall SoT = 95%**：`DEC-029` 的 94% 仅作 P2 过渡验收标注，不覆盖 Charter。
4. **`DEC-027` superseded-by `DEC-030`**：消除“不引入 O_DIRECT”与 FINE_DIRECT/诚实基准的双重真相；SPDK 远期评估由 DEC-030 继承。
5. **归档不删除**：已关闭提案/验证/冲突迁入 `spec/archive/2026-07/`。
6. **写入边界不变**：OpenClaw 整治 L0/L1/协议/SLA/决策；`50-verification` 与 L2 `refines` 委派 Claude Code。

## Alternatives considered

| 方案 | 为何拒绝 |
|------|----------|
| A. 静默把 Charter QPS 改成 130 | 抹掉 Buffered 合法生产路径，违反诚实协议的双报告精神 |
| B. 删除全部 Buffered SLA | 与 DEC-030/057“Buffered 仍为生产推荐”矛盾 |
| C. 引入外部 `ndf` CLI 强制 lint | 仓库尚无该工具链；本轮用 grep 门禁 + ADR 清单即可 |
| D. 重写全部 L2 为外部契约 | 超出防腐化范围，成本过高 |

## Consequences

- 固定目录 ID 唯一；`DEC-039` 可被 `CON-HONEST-002` 合法 `refines`。
- 性能叙事必须同时谈 Buffered 与 Honest；单报 Buffered 须附声明。
- `open/` 变薄；历史证据可追溯于 `archive/`。
- 后续 SLA 变更强制三联改：`40-constraints` + Charter + DEC/ADR。

## Anti-corruption checklist（常设）

1. 新条款落地前 `rg '\{#NEWID\}' spec/` 确认 ID 未占用。
2. `open/` 仅 Pending / 未答 Q / 未关闭 CONFLICT；Implemented → archive。
3. SLA 数字变更 → constraints + Charter + DEC/ADR。
4. 决策编号连续；跳号须占位或 gap 说明（本轮已用 DEC-039 填补 038→057 缺口之一；040–056 仍为历史 gap，不在本轮虚构）。

## Gap note (DEC numbering)

`DEC-040` … `DEC-056` 在仓库中无正文。本轮**仅物化被引用的 `DEC-039`**，不伪造中间编号。后续若需引用中间号，必须先落盘占位或说明 gap。
