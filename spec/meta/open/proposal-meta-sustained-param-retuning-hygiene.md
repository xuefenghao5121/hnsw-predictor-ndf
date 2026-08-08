> track: process
> status: proposal
> 日期: 2026-08-08

# 提案: 补全 sustained-param-retuning promote 后的 NDF 图卫生

## 背景

sustained-param-retuning 于 2026-08-07 promote (c63694f)，amend 了 API-011 和 API-017
（追加 sustained 调参推荐值），新增 DEC-086。但 promote 时未完成全部 NDF 图更新：

1. **trunk-ref 未更新**：API-011、API-017、CON-SLA-020 的 trunk-ref 仍指向旧 SHA
2. **depends-on 缺 DEC-086**：API-011、API-017 被 DEC-086 amend，但 depends-on 未追加
3. **CON-SLA-020 缺 DEC-086 依赖**：CON-SLA-020 depends-on API-011/API-017，经 DEC-086 amend 后应追加 DEC-086
4. **CON-SLA-016/017/018 同理**：均 depends-on API-011，trunk-ref 也需更新

## 变更清单

### spec/30-interfaces/env.md

#### API-011 (Benchmark / 调参环境变量)

| 字段 | 当前值 | 修正值 |
|------|--------|--------|
| trunk-ref | `d922f83` | `c63694f` |
| depends-on | `CON-002,DEC-073` | `CON-002,DEC-073,DEC-086` |

> 理由: DEC-086 amend 了 API-011 的 sustained 推荐值注释，trunk-ref 应指向包含该 amend 的 SHA。

#### API-017 (PQ 距离间隙自适应 EF 环境变量)

| 字段 | 当前值 | 修正值 |
|------|--------|--------|
| trunk-ref | `589e903` | `c63694f` |
| depends-on | `BEH-004` | `BEH-004,DEC-086` |

> 理由: DEC-086 amend 了 API-017 的 sustained 推荐值注释。

### spec/40-constraints/sla.md

#### CON-SLA-016 (SIFT1M 256MB SLA)

| 字段 | 当前值 | 修正值 |
|------|--------|--------|
| trunk-ref | `d922f83` | `c63694f` |
| depends-on | 追加 `DEC-086` | - |

#### CON-SLA-017 (SIFT1M 512MB SLA)

| 字段 | 当前值 | 修正值 |
|------|--------|--------|
| trunk-ref | `162377e` | `c63694f` |
| depends-on | 追加 `DEC-086` | - |

#### CON-SLA-018 (SIFT1M 256MB BG+Merge SLA)

| 字段 | 当前值 | 修正值 |
|------|--------|--------|
| trunk-ref | `edddd23` | `c63694f` |
| depends-on | 追加 `DEC-086` | - |

#### CON-SLA-019 (禁止预热被测 query)

| 字段 | 当前值 | 修正值 |
|------|--------|--------|
| trunk-ref | `47ed9e7` | 保持不变 |

> 理由: CON-SLA-019 的内容未被 DEC-086 修改，trunk-ref 指向其原始 promote SHA 仍然正确。

#### CON-SLA-020 (SIFT1M Sustained 基线 SLA)

| 字段 | 当前值 | 修正值 |
|------|--------|--------|
| trunk-ref | `47ed9e7` | `c63694f` |
| depends-on | 追加 `DEC-086` | - |

> 理由: CON-SLA-020 depends-on API-011/API-017，二者经 DEC-086 amend，
> trunk-ref 应指向包含 amend 的最新 SHA。
> 
> **基线数字不变**: CON-SLA-020 的基线用 EF=100 BASE 模式测得，仍为 BASE 模式参考基线。
> DEC-086 的 ADAPTIVE 最优 (EF=90+ADAPTIVE+eef=40) 是不同的配置，不替换 CON-SLA-020 基线。
> 在正文中追加 ADAPTIVE 模式参考性能，标注来源 DEC-086。

## 不变项

- **Trunk `src/` 代码不变** (sustained-param-retuning 本身就没改代码)
- **SLA 阈值数字不变** (基线数字仍有效)
- **CON-SLA-019 trunk-ref 不变** (内容未被 DEC-086 修改)

## 验收

- `ndf_index.py index` 通过
- `ndf_graphcheck.py` 0 error
- 所有被 amend 的 API/SLA 的 trunk-ref 指向 c63694f
- 所有被 amend 的 API/SLA 的 depends-on 包含 DEC-086

## source

> source: spec/decisions/22-sustained-param-retuning.md (DEC-086) ; git log c63694f
> track: process ; Topic: N/A (hygiene)
