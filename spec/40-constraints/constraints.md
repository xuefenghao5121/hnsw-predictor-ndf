# DiskHNSW — Constraints

> scope: product (40-constraints)
> status: stable | perf: not-established | bootstrap: adopt
> Observed Trunk SHA: `d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755`

本文件承载资源 / 物理 / 正确性约束。无测量证据的数字 MUST NOT 标为 stable must
（[[DEC-002]]）。SIFT1M sustained（[[CON-SLA-001]]）已确立；其余 `CON-SLA-*` 条款
`level=tbd`，数字须由 `spec/50-verification/` 协议产出后晋升。

## 内存预算约束 {#CON-001}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.1 source=observed -->

DiskHNSW MUST 在 cgroup `memory.max` 约束下运行，常驻内存（anon + file）不得突破
预算。测量以 cgroup `memory.peak` / `memory.stat` 为准，非 RSS-only。

## 召回目标 {#CON-002}
<!-- ndf: kind=constraint level=should layer=L1 status=stable since=0.1 source=observed -->

sustained 口径下 recall 目标 ≥95%。SIFT1M 已确立（实测 96.00%，见 [[CON-SLA-001]]）；
其余数据集须绑定测量证据（[[VER-006]]）。

## 吞吐声明纪律 {#CON-003}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.1 source=observed -->

对外吞吐声明 MUST 使用 sustained 口径；cache-warmed 口径（高估 1.73–7.60×）MUST NOT
作为商用吞吐对外引用，仅作回归护栏（[[DEC-002]]）。

## io_uring 线程安全 {#CON-004}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.1 source=observed -->

io_uring 非线程安全，多线程搜索 MUST 设 `FINE_PREAD=1` 以 pread 替代，否则 4T+ 崩溃
（[[BEH-013]]）。

## 数据配套一致性 {#CON-005}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.1 source=observed -->

vecblocks 与 route table 必须配套；blocks 与 vecblocks 的 block_id 各自独立路由表，
不得混用。graph 与 blocks 不同批将导致 recall 崩溃（[[API-011]]）。

## 架构平台约束 {#CON-006}
<!-- ndf: kind=constraint level=should layer=L1 status=stable since=0.1 source=observed -->

x86_64（AVX2）生产就绪；ARMv9 AArch64（NEON）代码就绪、待真实平台验证；标量为
fallback。ARM 128-bit SIMD 性能预期低于 x86 256-bit，多线程可弥补。

## SLA：SIFT1M sustained（stable） {#CON-SLA-001}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.1 source=measured -->

SIFT1M（128 维 / 1M）sustained 口径（[[VER-001]]）在 Trunk `d0ae5dd` × `cfg-sla-ef100` ×
cgroup 512MB × 16T 下实测（`spec/50-verification/baselines/bl-trunk-d0ae5dd.md`）：

| 指标 | 实测值 | 目标 |
|------|--------|------|
| Recall@10 | **96.00%** | ≥95% |
| 吞吐（agg QPS） | **4330.9** | — |
| steady QPS（Round 15） | **6448.0** | — |
| 常驻内存（anon RSS） | **352 MB** | ≤512MB cgroup |
| cgroup memory.peak | **512 MB**（触顶回收，`oom=0`） | ≤512MB |

> 内存效率（QPS/MB）与多线程扩展曲线仍 `not-established`，见 [[CON-SLA-003]]、
> [[CON-SLA-006]]。

## SLA：SIFT1M cache-warmed 回归（draft） {#CON-SLA-002}
<!-- ndf: kind=constraint level=tbd layer=L1 status=draft since=0.1 source=observed -->

cache-warmed 口径仅作为回归护栏（防性能倒退），其数字 not-established，不可对外引用。
回归基线绑定见 [[VER-002]]、[[VER-005]]。

## SLA：多线程扩展性（draft） {#CON-SLA-003}
<!-- ndf: kind=constraint level=tbd layer=L1 status=draft since=0.1 source=observed -->

1–24T 扩展曲线（DiskHNSW vs hnswlib unlimited）为 not-established；WILLNEED 后台线程
在 8T+ 推荐、12T+ 存在内核锁竞争，须以 sustained 复测。

## SLA：I/O 优化收益（draft） {#CON-SLA-004}
<!-- ndf: kind=constraint level=tbd layer=L1 status=draft since=0.1 source=observed -->

flat_vec_cache / WILLNEED / WILLNEED_BG / PAGE_MERGE_BG / VL_POOL 的收益在 cache-warmed
下被高估，MUST 以 sustained 口径重测后写入 baseline。PAGE_MERGE_BG 仅 256MB 推荐
（512MB 有害）。

## SLA：DEEP10M（draft） {#CON-SLA-005}
<!-- ndf: kind=constraint level=tbd layer=L1 status=draft since=0.1 source=observed -->

DEEP10M（96 维 / 10M）@2GB cgroup 可运行（hnswlib 全内存 OOM），recall ≥95% 目标
draft；sustained 口径测量待补。

## SLA：QPS/MB 内存效率（draft） {#CON-SLA-006}
<!-- ndf: kind=constraint level=tbd layer=L1 status=draft since=0.1 source=observed -->

内存效率（QPS per MB）对比 hnswlib 为 not-established；须以统一 cgroup 预算口径
（anon+file）测量后方可声明。
