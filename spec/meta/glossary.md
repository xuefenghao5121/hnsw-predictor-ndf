# Meta Glossary — 双轨 / 装订术语

> scope: ndf-process  
> 条款索引: `DEF-020`, `DEF-021`, `DEF-022`, `DEF-023`  
> 产品树 adopted 指针: `00-charter/glossary.md`

## DEF: POC（概念验证） {#DEF-020}
<!-- ndf: kind=def layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->

针对单一探索主题（通常对应一个 `proposal-*` / DEC 方向）的**可丢弃**实现与测量集合。
POC 的目标是产生证据（正/负），不是扩展生产 API 表面。承载面见 [[ARCH-008]]；纪律见 [[BEH-018]]。

## DEF: 晋升（Promote） {#DEF-021}
<!-- ndf: kind=def layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->

将 POC 中**已证实有效**的最小变更集，经提案确认后写入固定目录（stable 契约）并合入 `src/`
的过程。晋升 MUST 可追溯到证据与 DEC/提案 ID。闸门见 [[BEH-019]]。

## DEF: Topic Binder（主题装订器） {#DEF-022}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-020,ARCH-008,BEH-025 -->

某一 `poc/<topic>/` 探索主题的**进度与可复现入口**，目录为 `poc/<topic>/ndf/`
（含 `TOPIC.md`、`proposals/`、`evidence/`、`COMMITS.md`）。装订器 **不是** Trunk SoT
（`poc.sot: false`）；Trunk must 仍只在 `spec/00–50`。纪律见 [[BEH-025]]。

## DEF: Commit Ledger（提交账本） {#DEF-023}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-022,BEH-025 -->

`poc/<topic>/ndf/COMMITS.md` 中的对照表：将 `code_commit` 与（可选）`ndf_commit`、
提案 ID、条款 ID、验证协议绑定，使仅凭装订器即可定位如何复现该提交的测量结果。
