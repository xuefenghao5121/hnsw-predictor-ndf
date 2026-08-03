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

| 用例 | 配置 | 预期 | 实测 (2026-08-03) | 判定 |
|------|------|------|------|------|
| SIFT1M 严格隔离合规 | 512MB + drop_caches | peak≤512MB, oom=0, Recall≥95% | peak=512MB, oom=0, Recall=98.35% | ✅ 合规 |
| SIFT1M RSS 1T | 同上 | ≤300MB ([[CHR-006]]) | 235MB | ✅ |
| SIFT1M RSS 4T | 同上 | ≤450MB ([[CHR-006]] / [[DEC-066]]) | 416–426MB | ✅ |
| SIFT1M Buffered 1T QPS | 同上 | 观测基线（非 must） | **22.9** | 📌 对齐锚点 |
| SIFT1M Buffered 4T QPS | 同上 | 观测基线（非 must） | **18.4** | 📌 对齐锚点 |
| SIFT1M Honest 1T QPS | FINE_DIRECT=1 同上 | 观测基线（非 must） | **22.8** | 📌 对齐锚点 |
| SIFT1M Honest 4T QPS | FINE_DIRECT=1 同上 | 观测基线（非 must） | **19.5** | 📌 对齐锚点 |
| DEEP10M C 组严格隔离 | 2GB + drop_caches | peak≤2GB, oom=0, Recall≥95% | TBD | 待测 |

> 详细报告见 `spec/open/validation-20260803-strict-baseline.md`。
> 旧白嫖 QPS 废止与基线语义见 [[DEC-066]] / `proposal-strict-baseline-semantics.md`。
> QPS 行为后续优化的 R0；200 queries 为初版基线，加厚样本不改变协议。

> rationale: 现有 SLA 数字可能是在 page cache 白嫖条件下测得的，
> 需在严格隔离条件下验证以确保数字诚实性。见 [[DEC-065]]、
> `spec/open/proposal-strict-cgroup-test.md`。
> ID 说明：原提案误用 VER-035（已占用 FINE_PREAD）；本条款为 VER-039。
