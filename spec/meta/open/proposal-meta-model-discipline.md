# Proposal: MODEL 语义核纪律与 promote 触发 {#PROP-META-MODEL-DISCIPLINE}

> track: process  
> Status: Implemented on 2026-08-05  
> 日期: 2026-08-05  
> 关联: [[META-002]], [[META-003]], [[META-004]], [[ARCH-008]], [[BEH-019]], [[DEF-023]], [[ADR-META-002]]  
> 场景: 规范卫生 / 元分层  
> 原则: 产品无关；试点证据可引用产品 MODEL，条款正文不写产品专名

## 1. 动机

`model=` / `spec/models/` 仅为目录边界句（[[ARCH-008]]），缺目的、与 VER/ledger 分工、
以及 **promote 收口如何触发「要不要蒸馏语义核」**。产品试点已证明路径可行；纪律进 meta。

## 2. 决策

1. 新增 [[META-004]]（`language.md`）：预言机目的、分工、空槽、抽象非搬迁、触发纪律。
2. 加固 [[ARCH-008]]：禁 patch/ledger 入 models；允许空目录。
3. [[BEH-019]] 第 6 款：promote/partial **MUST 做决策**（要/不要/延期）；造核为 MAY；
   承载面为 `ndf_close plan`。
4. [`ndf_close.py`](../tools/ndf_close.py)：promote/partial 输出 §4b Semantic core；reject 为 N/A。
5. [`GOVERNANCE.md`](../tools/GOVERNANCE.md) §3 指针。

**不改**产品 `00–50` 条款正文；不把缺 `model=` 做成 graphcheck 硬错误；close 仍只读 plan。

## 3. 验收

- `ndf_graphcheck.py --meta` hard_errors=0；META-004 入 INDEX
- `ndf_close.py plan --mode promote` 含 Semantic core；`--mode reject` 无强制造核清单
