# DEC-001: adopt-mode 产品提案（Genesis 设计 hop） {#DEC-001}
<!-- ndf: kind=decision level=must layer=L0 status=draft since=0.1 source=observed -->

**Context.** `track=bootstrap`，`bootstrap_mode=adopt`。observed Trunk 为
`include/`（14 头文件）与 `src/`（core 3 + pipeline 12 + benchmark 3 + test 3）。
产品树原为 skeleton，本 hop 写入 draft 产品 NDF（00–50）。

**Decision.** 采用 adopt 模式：盘点既有 DiskHNSW 代码为 observed Trunk，写入 draft
产品 NDF（`status=draft`，性能 `not-established`），不建立 greenfield 初始主线，不改写
git 历史，不修改 `src/`、`include/`、`tests/`。

**Alternatives rejected.** greenfield 重建（改写既有代码，破坏历史）；legacy 三闸串行
（已被 [[META-009]] 废弃）。

**Source.** observed Trunk SHA `d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755`；
kernel bind record `spec/open/project-genesis/FOUNDATION.md`。

# DEC-002: 测量口径（sustained vs cache-warmed） {#DEC-002}
<!-- ndf: kind=decision level=must layer=L0 status=draft since=0.1 source=observed -->

**Context.** 早期文档的 30,332 / 18,675 QPS 为 cache-warmed 口径（200q + query 预热），
高估 1.73–7.60×。

**Decision.** 确立双口径纪律：sustained（`benchmark_sustained`，官方 10K query 池、禁预热）
为对外吞吐声明权威口径；cache-warmed（`benchmark_diskhnsw`，200q 预热）仅作回归护栏。
MUST NOT 混比（[[CON-003]]）。

**Alternatives rejected.** 仅用 cache-warmed（高估严重，误导商用定位）；废弃回归护栏
（失去防性能倒退手段）。

**Source.** observed `src/benchmark/benchmark_sustained.cpp` 与 README「测量口径说明」。
