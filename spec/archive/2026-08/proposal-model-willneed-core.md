# Proposal: WILLNEED 语义核 MODEL（promote 蒸馏试点） {#PROP-MODEL-WILLNEED-CORE}

> track: promote  
> Status: Implemented on 2026-08-05  
> 日期: 2026-08-05  
> Promotes: l4-cache-mgmt（语义核蒸馏；**不改 `src/`**）  
> 关联 TOPIC: `poc/l4-cache-mgmt/ndf/TOPIC.md`（[[BEH-025]]）  
> 关联: [[BEH-024]], [[API-012]], [[DEC-070]], [[ARCH-008]], [[META-002]], [[META-003]]  
> 依赖: `spec/archive/2026-08/proposal-promote-willneed.md`（已 Implemented）

## 1. 动机

WILLNEED 已晋升（DEC-070 / BEH-024 / `L4_WILLNEED`）。本仓 L3 长期由 VER 闭合，
`models/` 为空槽。本提案做一次**高价值 promote → 语义核 MODEL** 试点：把 WILLNEED
的可执行预言机从契约 rationale / 实现中蒸馏出来，经 `model=` 挂到 [[BEH-024]]。

## 2. 变更（仅 NDF）

| 路径 | 动作 |
|------|------|
| `spec/models/willneed-readahead.md` | 新增 `{#MODEL-WILLNEED-001}` L3 语义核 |
| `spec/20-behavior/search.md` [[BEH-024]] | `model=MODEL-WILLNEED-001`；WILLNEED 段指向语义核 |
| `spec/models/README.md` | 登记本金标 |
| `spec/ndf.yaml` | `id-prefixes` 含 `MODEL`；`layout.models` 列出文件 |

**MUST NOT**：改 `src/`、搬迁 poc、写入 git patch 账本、改 VER。

## 3. 语义核边界

纳入：启用条件、时机、`posix_fadvise(WILLNEED)` 操作、不变量（默认关、不减 I/O 量等）。  
不纳入：QPS/cgroup 证据表（仍在 [[DEC-070]]）、COMMITS、实现文件路径。

## 4. 验证

- `python3 spec/meta/tools/ndf_index.py index` + `validate`
- 无 Trunk 代码变更 → **跳过**场景 5/6（validation/perf = n/a）
