# DiskHNSW — Verification

> scope: product (50-verification)
> status: stable | perf: not-established | bootstrap: adopt
> Observed Trunk SHA: `d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755`

本文件定义验证协议与配置 / 基线注册表指针。可移植布局：锁定
**代码 SHA × 配置身份 × 测量数字**（见父 `spec/50-verification/README.md`）。

## sustained 权威口径 {#VER-001}
<!-- ndf: kind=verif level=must layer=L1 status=stable since=0.1 source=observed -->

对外吞吐 / 召回声明 MUST 使用 `benchmark_sustained`（[[API-012]]）：

- 官方 SIFT 10K query 池，多轮随机采样（N=1000, R=15, seed=42）。
- 禁止对被测 query 预热（`sync; echo 3 > /proc/sys/vm/drop_caches`）。
- recall 以 official ground truth 计算。

## cache-warmed 回归护栏 {#VER-002}
<!-- ndf: kind=verif level=must layer=L1 status=stable since=0.1 source=observed -->

`benchmark_diskhnsw`（200q + query 预热）仅用于回归测试防性能倒退，其数字 MUST NOT
对外引用为商用吞吐（[[CON-003]]）。

## cgroup 隔离测量 {#VER-003}
<!-- ndf: kind=verif level=must layer=L1 status=stable since=0.1 source=observed -->

内存测量 MUST 在 cgroup v1/v2 隔离下进行（`scripts/cgroup_utils.sh`），读取
`memory.peak` 与 `memory.stat`（anon/file/workingset_refault_file/pgmajfault）。

## 配置注册表 {#VER-004}
<!-- ndf: kind=verif level=must layer=L1 status=stable since=0.1 source=observed -->

每个测量配置 MUST 以 `cfg-<id>.md` 记录完整测量旋钮 / 环境
（`spec/50-verification/configs/`），包括 `TWO_STAGE`、`FINE_*`、`L4_*`、`CACHE_MB`、
`FLAT_VEC_MB`、`REFINE_EF`、线程数、cgroup 预算等。

## 基线注册表 {#VER-005}
<!-- ndf: kind=verif level=must layer=L1 status=stable since=0.1 source=observed -->

每个观测性能线 MUST 以 `bl-trunk-<shortsha>.md` 记录 trunk SHA + config_id + 数字
（`spec/50-verification/baselines/`）；禁止静默改写已引用基线 ID。金标指针见
`golden-baseline.md`。

## 召回验证 {#VER-006}
<!-- ndf: kind=verif level=must layer=L1 status=stable since=0.1 source=observed -->

召回 MUST 以真实 ground truth（`scripts/gen_gt.py`）对 top-K 计算；PQ 的 M 与维度不匹配
导致 recall≈0%，graph 与 blocks 不配套导致 recall 崩溃，均视为失败（[[CON-005]]）。

## 单元 / 质量测试 {#VER-007}
<!-- ndf: kind=verif level=should layer=L1 status=stable since=0.1 source=observed -->

SHOULD 运行 `make test`（`test_block_cache`、`test_disk_hnsw`、`test_pq_search_quality`）
验证块缓存、检索正确性与 PQ 搜索质量。

## 复现与证据义务 {#VER-008}
<!-- ndf: kind=verif level=must layer=L1 status=stable since=0.1 source=observed -->

任何性能结论 MUST 可复现：绑定 Trunk SHA、配置身份、基准入口与数字；原始 evidence、
脚本与 git SHA 作为审计证据留存（`spec/50-verification/` 与 `results/`）。
