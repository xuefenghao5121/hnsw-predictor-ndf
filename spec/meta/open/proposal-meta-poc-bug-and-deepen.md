# Proposal: POC 中主线 Bug 与探索延长管理 {#PROP-META-POC-BUG-AND-DEEPEN}

> track: process  
> Status: Implemented on 2026-08-05  
> 日期: 2026-08-05  
> 关联: [[CHR-008]], [[BEH-018]], [[BEH-019]], [[BEH-020]], [[BEH-025]], [[ARCH-008]], [[DEF-020]], [[DEF-021]], [[DEF-022]], [[DEF-NDF-BINDER-DUAL-HEAD]], [[ADR-META-001]]  
> 场景: 规范卫生 / 双轨可追踪性  
> 先例: `poc/l4-cache-mgmt`（O_DIRECT 4T bug → DEC-068；WILLNEED partial promote → DEC-070）

## 1. 动机

探索过程中常出现两类需求，现行条款有支撑但口令不够显式：

1. **POC 中发现 Trunk 主线 bug**：应在 `poc/<topic>/` 修测取证，再决定是否合入；与「直接 `track=bug` 改 `src/`」易混淆。
2. **探索延长 / 深入对话**：是否要嵌套「子 POC → 多层 promote 到上层」？会引入装订器双头风险（[[DEF-NDF-BINDER-DUAL-HEAD]]），且 promote 目标永远是 Trunk，不是父 POC。

本提案把已验证的扁平管理模型写进 process profile，减少歧义。

## 2. 决策摘要

### 2.1 POC 中发现的主线 Bug

1. **默认路径**：在当前主题登记 bug 切片（TOPIC 进展 / Next gate；必要时 `amend` 提案）→ 仅改 `poc/<topic>/`（或 POC 分支）→ 用主题 `baseline_protocol` 验证 → 若合入则开产品提案 `track: bug`（或挂在 promote 干净切片）→ 干净合入 `src/` → `ndf_close plan --mode partial`（主题可继续 `exploring`）。
2. **不合入**：留 POC / NOTES；主题 reject 时按 [[BEH-020]]；bug 切片可另开独立 bug 提案。
3. **紧急直修 Trunk**：仅当已确认是 Trunk 缺陷、与当前探索假设无关、且需尽快修生产路径时，允许 `track=bug` 直改 `src/`，事后补 DEC/VER。日常「探索时顺手发现」MUST 优先走默认路径。

### 2.2 探索延长：禁止嵌套子 POC

1. **同一假设 / 同一 baseline_protocol**：留在同一 `poc/<topic>/`——v1→v2…、`amend` 提案、evidence 追加、可选 `ndf_close --mode partial`。
2. **假设分叉**（新机制、新 SLA 面、强依赖另一主题）：新建**平级** `poc/<new-topic>/`，TOPIC 写 `depends_on_topics: […]`；各自独立 promote/reject。
3. **MUST NOT** 建立父子「子 POC」目录树，也 **MUST NOT**「promote 进父 POC」。Promote 目标仅为 Trunk `src/` + `spec/00–50`。

## 3. 变更清单（确认后落地）

| 位置 | 动作 |
|------|------|
| [`spec/meta/process.md`](../process.md) [[BEH-018]] | 新增第 8 条：POC 中发现的 Trunk 缺陷默认在本主题修测；合入走 `track=bug`/`promote` + 干净合入 + 可选 partial；紧急直修例外 |
| [`spec/meta/process.md`](../process.md) [[BEH-025]] TOPIC 段 | 明确探索延长用同主题 amend / partial；分叉用平级 topic + `depends_on_topics`；**禁止**嵌套子 POC / promote-to-parent |
| [`AGENTS.md`](../../AGENTS.md) §6.1 / §6.2a | 薄指针：POC-discovered bug 口令；探索延长不嵌套子 POC |
| 本文件 | Pending → Implemented（确认后） |

不新增条款 ID（不另开 BEH-027）；用既有 [[BEH-018]] / [[BEH-025]] 增补 must 行。不改产品 `20-behavior/`。

## 4. 非目标

- 不改 `ndf_close.py` 行为（`partial` 已够用）
- 不强制所有历史 bug 补装订器记录
- 不引入 Harness / 可移植包同步（本地 process 优先）

## 5. 验收

- [[BEH-018]] 可读出「POC 内 bug → 可选合入」默认路径与紧急例外
- [[BEH-025]] 可读出「amend / partial / 平级 depends_on；禁止嵌套子 POC」
- `AGENTS.md` 场景路由与上述一致
- 与 `l4-cache-mgmt` 先例叙事不矛盾

## 6. 拟写入条款草案（确认后剪切）

### BEH-018 新增第 8 条

```text
8. 探索中发现的 Trunk 缺陷（主线 bug）：默认 MUST 在当前 `poc/<topic>/` 登记为 bug
   切片并修测取证（TOPIC / amend 提案 / COMMITS）；MUST NOT 为「顺便修 bug」绕过本条
   第 6 款直接改生产默认路径。确认合入时 MUST 开产品提案（track=bug 或挂 promote
   干净切片），干净合入 `src/`，并可用 `ndf_close --mode partial` 收口子集而主题继续
   exploring。仅当缺陷已确认与当前假设无关且需紧急修生产路径时，允许 track=bug
   直改 Trunk，事后 MUST 补 DEC/VER。
```

### BEH-025 TOPIC 段追加

```text
### 探索延长与主题边界

- 同一假设与同一 `baseline_protocol` 下的深入（含对话延长需求）MUST 留在同一主题：
  追加 evidence、`amend` 提案、可选 partial promote。
- 假设或验收面分叉时 MUST 新建平级 `poc/<other-topic>/`，并用 `depends_on_topics[]`
  声明依赖；各自主题独立 promote/reject。
- MUST NOT 嵌套「子 POC」目录，也 MUST NOT 将子主题「晋升」进父 POC 目录。
  Promote 目标仅为 Trunk（[[BEH-019]]）。
```
