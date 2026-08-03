# Proposal: NDF 探索轨（POC）与主线晋升闸门

> 日期: 2026-08-01
> 场景: 场景1 增量特性（流程/章程级）
> Status: Implemented on 2026-08-01
> 触发: Read Coalescing 等方向「多轮深入 → 负结果回退」导致 NDF 与 `src/` commit 漂移
> 关联: [[DEC-061]]（负结果样板）、[[CHR-008]] / [[ARCH-008]] / [[BEH-018]]…[[BEH-020]]

## 问题

沿同一 `proposal-*` 方向会**多轮深入探索**。若过早把 L1/`src/` 合入主线，方向证伪后
NDF 可回退但代码 commit 仍挂主线 → SoT 与实现漂移。

## 已落地

| ID | 文件 |
|----|------|
| [[CHR-008]] | `00-charter/charter.md` |
| [[DEF-020]] [[DEF-021]] | `00-charter/glossary.md` |
| [[ARCH-008]] | `10-architecture/modules.md` |
| [[BEH-018]]…[[BEH-020]] | `20-behavior/process.md` |
| [[CON-POC-001]] | `40-constraints/sla.md` |
| ADR | `decisions/adr-poc-track.md` |
| 骨架 | `poc/README.md`, `spec/models/README.md` |
| 清单 | `ndf.yaml`, `README.md` |

## 工作流

```text
open/proposal ──► poc/<topic>/ 多轮实验 ──► 证据
                      │                    │
                      │ 负结果             │ 正结果
                      ▼                    ▼
                 DEC 关闭 + 弃条款      stable + 干净合入 src/
```

**不**移动历史 `src/`；RC 关闭见 [[DEC-061]]。
