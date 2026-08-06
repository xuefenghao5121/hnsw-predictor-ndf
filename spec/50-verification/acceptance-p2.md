# P2 DEEP10M 验证用例

> Note: 表中 ≥94% 行为 **P2 过渡验收**（[[DEC-029]]）；Charter / CON SoT 仍为 ≥95%（[[CHR-006]]）。

## VER-034: VisitedList uint32 -> uint8 {#VER-034}
<!-- ndf: kind=verif level=must layer=L3 status=stable since=0.4 verifies=DEC-034 source=observed -->

| 用例 | 配置 | 预期 | 实测 | 判定 |
|------|------|------|------|------|
| Recall 不变 | EF=300, T=1 | 95.15% ± 0.0pp | 95.15% | ✅ |
| QPS 提升 (1T) | EF=300, T=1 | ≥ 1.5x | 2.1x (283->590) | ✅ |
| QPS 提升 (T=20) | EF=300, T=20 | ≥ 3x | 4.5x (528->2374) | ✅ |
| Recall 梯度正确 | EF=100/200/300/400 | 单调递增 | 90.85/94.20/95.15/95.55% | ✅ |
| 内存节省 (T=20) | VisitedList 总量 | ≤ 200MB | 200MB (vs 800MB) | ✅ |

## VER-035: FINE_PREAD io_uring bug 修复 {#VER-035}
<!-- ndf: kind=verif level=must layer=L3 status=stable since=0.4 verifies=DEC-035,BEH-001 source=observed -->

| 用例 | 配置 | 预期 | 实测 | 判定 |
|------|------|------|------|------|
| io_uring EF=200 | FINE_PREAD=0 | 94.20% (P2 过渡) | 94.20% | ✅ (正常) |
| io_uring EF=300 | FINE_PREAD=0 | ≥94% (P2 过渡) | 88.40% | ❌ (bug) |
| io_uring EF=400 | FINE_PREAD=0 | ≥94% (P2 过渡) | 70.80% | ❌ (bug) |
| pread EF=200 | FINE_PREAD=1 | 94.20% (P2 过渡) | 94.20% | ✅ |
| pread EF=300 | FINE_PREAD=1 | ≥95% (Charter SoT) | 95.15% | ✅ |
| pread EF=400 | FINE_PREAD=1 | ≥95% (Charter SoT) | 95.55% | ✅ |
| 多线程安全 | FINE_PREAD=1, T=12 | recall 不变 | 95.15% | ✅ |

## VER-036: PQ dsub=3 SIMD {#VER-036}
<!-- ndf: kind=verif level=should layer=L3 status=stable since=0.4 verifies=DEC-036,BEH-006 source=observed -->

| 用例 | 配置 | 预期 | 实测 | 判定 |
|------|------|------|------|------|
| Recall 不变 | EF=300, SIMD on | 95.15% ± 0.0pp | 95.15% | ✅ |
| QPS 提升 | EF=300, T=1 | ≥ 0% (不退化) | +1.4% (283->286) | ✅ |
| QPS 提升 (T=12) | EF=300, T=12 | ≥ 0% | +1.4% (480->487) | ✅ |

## VER-037: DEEP10M cgroup 内存 {#VER-037}
<!-- ndf: kind=verif level=must layer=L3 status=stable since=0.4 verifies=DEC-037,CHR-006 source=observed -->

| 用例 | 配置 | 预期 | 实测 | 判定 |
|------|------|------|------|------|
| 2GB cgroup recall | T=4, EF=300 | ≥95% | 95.15% | ✅ |
| 2GB cgroup QPS | T=4 | ≥500 | 1484 | ✅ |
| 2GB cgroup QPS (T=12) | T=12 | ≥500 | 2340 | ✅ |
| 2GB cgroup RSS | peak | ≤2GB | 1612MB | ✅ |
| 1.8GB cgroup | T=4 | 正常运行 | 941/1395MB, 1483 QPS | ✅ |
| 1.5GB cgroup | T=4 | - | OOM (SIGKILL) | ❌ (预期) |
| 1GB cgroup | T=4 | - | OOM (SIGKILL) | ❌ (预期) |
| hnswlib 2GB ef=50 | ef=50, 50q | 存活 | RSS 2025MB, 85.50% recall | ✅ |
| hnswlib 2GB ef=200 | ef=200, 200q | OOM | SIGKILL | ✅ (DiskHNSW 优势) |

## VER-038: 图裁剪 10M 负结果 {#VER-038}
<!-- ndf: kind=verif level=should layer=L3 status=stable since=0.4 verifies=DEC-038 source=observed -->

| 用例 | 配置 | 预期 | 实测 | 判定 |
|------|------|------|------|------|
| R_max=24 recall | EF=300 | ≥95% (Charter) / P2 过渡可接受 ≥94% | 94.90% | ⚠️ -0.25pp vs Charter |
| R_max=24 recall | EF=400 | ≥95% | 95.30% | ✅ (需更高 EF) |
| R_max=24 CSR | - | <591MB | 522MB (-69MB) | ✅ |
| R_max=24 QPS | EF=300 | ≥590 | 624 (+6%) | ✅ |
| R_max=20 recall | EF=300 | ≥94% (P2 过渡) | 94.45% | ⚠️ -0.7pp vs Charter |
| R_max=20 CSR | - | <522MB | 481MB (-110MB) | ✅ |
| 结论 | - | 不合入主线 | recall 损失 > QPS 收益 | ✅ 决策 |

## 严格隔离验收 {#VER-039}
<!-- ndf: kind=verification level=must layer=L1 status=stable since=0.9 source=deduced -->
<!-- ndf: verifies=CON-SLA-014,CHR-006,CON-SLA-011 depends-on=DEC-065 -->

[[CHR-006]] 和 [[CON-SLA-011]] 中的所有 QPS/Recall/RSS 指标 MUST 在
[[CON-SLA-014]] 严格 cgroup 隔离条件下验证（或重新验证）。

验收报告 MUST 包含：
1. cgroup `memory.peak`（证明总内存未超限）
2. cgroup `memory.stat` 中的 `anon` 和 `file` 分项（证明 page cache 在预算内）
3. `memory.events` 中的 `oom` 计数（证明未触发 OOM）
4. [可选] `fincore`/`vmtouch` 文件缓存验证

| 用例 | 配置 | 预期 | 实测 (2026-08-03, [[DEC-067]]) | 判定 |
|------|------|------|------|------|
| SIFT1M 严格隔离合规 | 512MB + drop_caches | peak≤512MB, oom=0, Recall≥95% | peak=512MB, oom=0, Recall=95.75% | ✅ 合规 |
| SIFT1M RSS 1T | 同上 | ≤300MB ([[CHR-006]]) | 155MB | ✅ |
| SIFT1M RSS 4T | 同上 | ≤450MB ([[CHR-006]]) | 161MB | ✅ |
| SIFT1M Buffered 1T QPS | 同上 | ≥2000 ([[CHR-006]]) | **2309** | ✅ |
| SIFT1M Buffered 4T QPS | 同上 | ≥5000 ([[CHR-006]]) | **6060** | ✅ |
| SIFT1M Honest 1T QPS | FINE_DIRECT=1 同上 | ≥100 ([[CON-SLA-011]]) | **837** | ✅ |
| SIFT1M Honest 4T QPS | FINE_DIRECT=1 同上 | ≥400 ([[CON-SLA-011]]) | **3215** (recall=13.95%⚠️) | ⚠️ QPS达标recall异常 |
| DEEP10M C 组严格隔离 | 2GB + drop_caches | peak≤2GB, oom=0, Recall≥95% | peak=2GB, oom=0, Recall=95.05% | ✅ 合规 |
| DEEP10M Buffered 1T QPS | 同上 | 观测基线 | **580** | 📌 基线 |
| DEEP10M Buffered 4T QPS | 同上 | 观测基线 | **1562** | 📌 基线 |
| DEEP10M O_DIRECT 1T QPS | FINE_DIRECT=1 同上 | 观测基线 | **43** | 📌 基线 |
| DEEP10M RSS 1T | 同上 | - | 1156MB | ✅ |
| DEEP10M RSS 4T | 同上 | - | 1205MB | ✅ |

> DEC-066 假基线（22.9 等）因 PQ_CODES_PATH 拼写错误废止，见 [[DEC-067]]。
> 修正后旧 SLA 数字在严格隔离下仍然有效。详细报告见
> `spec/archive/2026-08/validation-20260803-strict-baseline.md`（open 仅 stub）。

> rationale: 现有 SLA 数字可能是在 page cache 白嫖条件下测得的，
> 需在严格隔离条件下验证以确保数字诚实性。见 [[DEC-065]]、
> `spec/archive/2026-08/proposal-strict-cgroup-test.md`。
> ID 说明：原提案误用 VER-035（已占用 FINE_PREAD）；本条款为 VER-039。

## CON-SLA-016 验收（256MB 紧凑配置） {#VER-040}
<!-- ndf: kind=verification level=must layer=L1 status=stable since=0.9 source=observed -->
<!-- ndf: verifies=CON-SLA-016 depends-on=CON-SLA-014,API-011,API-012 trunk-ref=d922f8388e3769072ad6f7f621f1a54f45ca26da -->

[[CON-SLA-016]] MUST 在 [[CON-SLA-014]] 严格隔离下、下列测量配置复现：

| 项 | 值 |
|----|-----|
| cgroup | 256MB + drop_caches |
| env（测量） | `L4_WILLNEED=1 FINE_PREAD=1 FLAT_VEC_MB=64 CACHE_MB=64 REFINE_EF=100 NUM_THREADS=4` |
| Trunk | `trunk-ref=d922f8388e3769072ad6f7f621f1a54f45ca26da` |
| QPS / Recall / oom / peak | 见 [[CON-SLA-016]] |

旋钮接口：[[API-011]] [[API-012]]。证据：`poc/perf-gap-4t/ndf/evidence/d6-256mb-cgroup-20260805.md`。

## CON-SLA-017 验收（512MB A2+C2） {#VER-041}
<!-- ndf: kind=verification level=must layer=L1 status=stable since=0.9.5 source=observed -->
<!-- ndf: verifies=CON-SLA-017 depends-on=CON-SLA-014,API-011,API-012,API-013 trunk-ref=162377ee75dbb6a3042572bce47686b92a86aa42 -->

| 项 | 值 |
|----|-----|
| cgroup | 512MB + drop_caches |
| env（测量） | `L4_WILLNEED=1 WILLNEED_BG=1 VL_POOL_THREADS=14 FINE_PREAD=1 FLAT_VEC_MB=160`（+ 适用时 `NUM_THREADS=16`） |
| Trunk | `trunk-ref=162377ee75dbb6a3042572bce47686b92a86aa42` |
| QPS / Recall / oom | 见 [[CON-SLA-017]] |

旋钮接口：[[API-011]] [[API-012]] [[API-013]]。证据：`poc/multi-thread-scaling/ndf/evidence/comprehensive-sweep-20260805.md`。

## CON-SLA-018 验收（256MB BG+Merge） {#VER-042}
<!-- ndf: kind=verification level=must layer=L1 status=stable since=0.9.6 source=observed -->
<!-- ndf: verifies=CON-SLA-018 depends-on=CON-SLA-014,API-011,API-012,API-013 trunk-ref=edddd232947c5ec5bde27065add3b1a60621cb80 -->

| 项 | 值 |
|----|-----|
| cgroup | 256MB + drop_caches |
| env（测量） | `L4_WILLNEED=1 WILLNEED_BG=1 PAGE_MERGE_BG=1 VL_POOL_THREADS=14 FLAT_VEC_MB=64`（+ 适用时高并发线程数） |
| Trunk | `trunk-ref=edddd232947c5ec5bde27065add3b1a60621cb80` |
| QPS / Recall / oom | 见 [[CON-SLA-018]] |

旋钮接口：[[API-011]] [[API-012]] [[API-013]]。证据：`poc/l4-cache-mgmt/ndf/evidence/d2-bg-page-merge-20260805.md`。

## CON-SLA-020 验收（SIFT1M sustained 基线） {#VER-043}
<!-- ndf: kind=verification level=must layer=L1 status=stable since=0.9.10 source=observed topic=sustained-query-benchmark -->
<!-- ndf: verifies=CON-SLA-020,CON-SLA-019,BEH-035 depends-on=CON-SLA-014,API-019,API-011,API-012,API-013 trunk-ref=47ed9e7 -->

| 项 | 值 |
|----|-----|
| cgroup | 512MB / 256MB + drop_caches（每组前清场） |
| harness | `benchmark_sustained`（[[API-019]]）；MUST NOT 用含 query 预热的 harness |
| query pool | `data/sift_query_official10k.fvecs`（官方 10K） |
| groundtruth | `data/sift_groundtruth_official.ivecs`（官方） |
| 采样 | `--per-round 1000 --rounds 15 --seed 42`（`--warmup 0`） |
| env（测量） | `TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1 REFINE_EF=100 PAGE_MERGE_BG=1 L4_WILLNEED=1 WILLNEED_BG=1 VL_POOL_THREADS=14 FLAT_VEC_MB=160(512MB)/64(256MB) NUM_THREADS={1,4,16}` |
| Trunk | `trunk-ref=47ed9e7` |
| QPS / Recall / oom | 见 [[CON-SLA-020]] |

### 通过判据

1. Recall@10 ≥ 95%（基线 96.00%）
2. 聚合 QPS ≥ [[CON-SLA-020]] 表中 SLA 列
3. `memory.events` 中 `oom` = 0
4. 报告同时给出聚合与末轮（稳态）QPS
5. **不变量 I1**（[[MODEL-SUSTAINED-001]]）：抽查 `N ∈ {200, 10000}` 时稳态 QPS
   与 `N=1000` 在噪声范围内一致

### 复现

```bash
for MB in 512 256; do for T in 1 4 16; do
  TAG=ver043 CGROUP_MB=$MB THREADS=$T PER_ROUND=1000 ROUNDS=15 \
    bash scripts/run_sustained.sh
done; done
```

参考语义：[[MODEL-SUSTAINED-001]]。禁预热约束：[[CON-SLA-019]]。
证据：`poc/sustained-query-benchmark/ndf/evidence/r3-r5-sweep-20260806.md`。

## hnswlib 全内存对照验收 {#VER-044}
<!-- ndf: kind=verification level=should layer=L1 status=stable since=0.9.10 source=observed topic=sustained-query-benchmark -->
<!-- ndf: verifies=CON-HONEST-002 depends-on=CON-SLA-019,MODEL-SUSTAINED-001 trunk-ref=47ed9e7 -->

对外声明「vs hnswlib」时的对照口径（[[MODEL-SUSTAINED-001]] 不变量 I6）。

| 项 | 值 |
|----|-----|
| hnswlib 内存 | unlimited（不设 cgroup，代表 in-memory 天花板） |
| query pool | 与 DiskHNSW **同一** 官方 10K 池 |
| groundtruth | 与 DiskHNSW **同一** 官方 GT（k=10 转换格式） |
| 清场 | 每组前 `drop_caches` |
| 报告 | MUST 给出 QPS / Recall / RSS 三元组 + QPS/MB |

### 基线（2026-08-06）

| 线程 | QPS | Recall@10 | RSS |
|------|-----|----------|-----|
| 1T | 6,423.6 | 98.25% | 734 MB |
| 4T | 22,757.0 | 98.25% | 739 MB |
| 16T | 42,947.1 | 98.25% | 763 MB |

### MUST NOT

MUST NOT 用 cache-warmed 口径的 DiskHNSW 数字与本对照做比值
（会得出错误的 QPS/MB 优势结论，见 [[DEC-084]] §7）。

证据：`poc/sustained-query-benchmark/ndf/evidence/r6-hnswlib-comparison-20260806.md`。
