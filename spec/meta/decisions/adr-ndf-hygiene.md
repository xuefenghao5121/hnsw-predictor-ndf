# ADR: NDF 规范防腐化与双轨 SLA {#DEC-HYGIENE-001}

> 日期: 2026-07-31
> 状态: Accepted
> 关联提案: `spec/open/proposal-ndf-hygiene.md`
> 场景: 场景3（项目重构）

## Context

`spec/` 在快速迭代（P2、冷 I/O、O_DIRECT 诚实基准）后出现结构性腐化：条款 ID 撞车、幽灵决策 `DEC-039`、`OBS-*`/`INTENT-*` 死链、Charter 无模式 QPS 与 Honest 实测冲突、`open/` 堆积已落地文件。若继续在腐化图上叠加条款，精化链与验证覆盖将不可审计。

## Decision

1. **先图后语义**：优先消除重复 ID、物化被引用的幽灵决策、重写 `ndf.yaml` 前缀、重定向死链，
   再调和 SLA 与归档（产品侧细节见 `spec/40-constraints/`、`spec/decisions/`、`spec/archive/`）。
2. **SLA 双轨（不静默删旧数字）**：产品树 MUST 区分 Buffered 生产路径与诚实/直接 I/O 验收路径；
   具体阈值与条款 ID 以产品 `spec/40-constraints/sla.md` 与 Charter 为准，本 ADR 不嵌入产品数字。
3. **Recall SoT**：以产品 Charter 为准；过渡验收标注不得覆盖 Charter。
4. **消除双重真相**：冲突的 I/O 架构 DEC 须用 `superseded-by` 收口（产品 `spec/decisions/`）。
5. **归档不删除**：已关闭提案/验证/冲突迁入 `spec/archive/`。
6. **写入边界不变**：OpenClaw 整治 L0/L1/协议/SLA/决策；`50-verification` 与 L2 `refines` 委派 Claude Code。

## Alternatives considered

| 方案 | 为何拒绝 |
|------|----------|
| A. 静默改写 Charter QPS | 抹掉合法生产路径，违反诚实双报告精神 |
| B. 删除全部 Buffered SLA | 与「Buffered 仍为生产推荐」的产品 DEC 矛盾 |
| C. 引入外部 `ndf` CLI 强制 lint | 当时仓库尚无该工具链；本轮用门禁 + ADR 清单 |
| D. 重写全部 L2 为外部契约 | 超出防腐化范围，成本过高 |

## Consequences

- 固定目录 ID 唯一；产品诚实条款可合法 `refines` 对应产品 DEC（见产品树）。
- 性能叙事必须同时谈 Buffered 与 Honest；单报 Buffered 须附声明。
- `open/` 变薄；历史证据可追溯于 `archive/`。
- 后续 SLA 变更强制三联改：`40-constraints` + Charter + DEC/ADR。

## Anti-corruption checklist（常设）

1. 新条款落地前 `rg '\{#NEWID\}' spec/` 确认 ID 未占用。
2. `open/` 仅 Pending / 未答 Q / 未关闭 CONFLICT；Implemented → archive。
3. SLA 数字变更 → constraints + Charter + DEC/ADR。
4. 决策编号连续；跳号须占位或 gap 说明（历史 gap 见产品 `spec/decisions/`，不在此虚构）。

## Gap note (DEC numbering)

历史 DEC 编号缺口的正文物化规则见产品 `spec/decisions/`；本 ADR 不枚举产品 ID。
