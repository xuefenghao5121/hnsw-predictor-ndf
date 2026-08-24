# Proposal: POC 内 NDF 呈现面与阅读顺序（装订器唯一入口）
{#PROP-POC-NDF-PRESENTATION-SURFACE}

> track: process
> Status: Implemented on 2026-08-04
> 日期: 2026-08-04
> 关联: [[BEH-025]], [[ARCH-008]], [[CON-POC-001]], [[DEF-022]], [[DEF-023]]
> 场景: 规范卫生 / 双轨可读性

## 1. 动机

当 POC 的“文档分支/代码分支”拆开独立维护时，协作者容易把 POC 内的散文、`spec/open/` stub、以及 README 里的描述混当成“第二棵 Trunk SoT”。

本提案目的是把你在 POC 中的 NDF 呈现建议固化成明确纪律：**POC 内唯一可读 NDF 呈现面是装订器 `poc/<topic>/ndf/`，其阅读顺序、以及 README 仅导航而不复述 must**。

## 2. 决策摘要

1. POC 主题级 NDF 呈现以 `poc/<topic>/ndf/` 为唯一入口（非 Trunk SoT），并给出推荐阅读顺序。
2. `poc/<topic>/README.md` 仅作为三行导航，不复述任何 `status=stable` 的 must 正文；所有规范性内容以 `ndf/TOPIC.md` 与 `ndf/proposals/` 为准。

## 3. 变更清单（拟）

| 位置 | ID/锚点 | 动作 |
|------|----------|------|
| `spec/meta/process.md` | BEH-025 | 在 `TOPIC.md` 说明附近新增“阅读顺序与唯一入口”子段（MUST 约束） |
| `spec/meta/architecture.md` | ARCH-008 | 追加一句强调：装订器用于呈现与复现路径，不得被当作 stable must 源 |
| `poc/README.md` | 用法 section | 新增三行导航文本（明确 pointer，不复述 must） |

## 4. 具体新增约束（建议写入）

### 4.1 BEH-025：POC 内唯一呈现面与阅读顺序

在 `BEH-025` 的 `TOPIC.md` / 装订器说明附近新增（示例文案，供落地时直接引用）：

1. `poc/<topic>/ndf/` MUST 作为 POC 内唯一规范性呈现面；`poc/<topic>/README.md` MUST NOT 成为 must 源。
2. 协作者在 POC 内获取 NDF 的推荐阅读顺序 MUST 为：
   1. `poc/<topic>/ndf/TOPIC.md`
   2. `poc/<topic>/ndf/proposals/`（或 stub 指向 `spec/open/`）
   3. `poc/<topic>/ndf/evidence/`
   4. `poc/<topic>/ndf/COMMITS.md`
3. 所有 POC 数字与验证结论 MUST 以 `evidence/` 为载体；不得把 `evidence/` 中的数字直接搬到 README 当“口径承诺”。

### 4.2 ARCH-008：装订器的角色边界

在 ARCH-008 “models 与 poc 边界”附近追加一句（示例）：

> 装订器 `poc/<topic>/ndf/` 仅用于探索进度呈现与复现路径入口，不得被当作 Trunk `spec/00-50` 的 `status=stable` must 源。

### 4.3 `poc/README.md`：三行导航（不复述 must）

建议在 `poc/README.md` `用法` section 的 `poc/<topic>/` 样板后追加三行（示例，落地时可按实际路径微调）：

```text
NDF（唯一呈现面）：poc/<topic>/ndf/TOPIC.md
复现与口径：poc/<topic>/ndf/COMMITS.md + ndf/evidence/
Trunk must 仍在：spec/00-50（status=stable）
```

并加入一条提醒：`README.md` 仅导航，不复述 must 正文；规范性陈述以 `ndf/` 与 `spec/` 为准。

## 5. 非目标

- 不修改任何现有 `status=stable` must 的条款数字与验收门槛。
- 不改变 `poc/<topic>/` 的目录结构（仅对呈现层做纪律补强）。

