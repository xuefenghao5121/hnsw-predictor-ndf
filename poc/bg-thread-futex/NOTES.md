# NOTES: bg-thread-futex

> status: exploring
> 开题: 2026-08-09
> Trunk SHA: 4697c0d

## Baseline (R0 参考)

| 配置 | Agg QPS | Steady QPS | Recall | sched_yield/q |
|------|---------|-----------|--------|---------------|
| BG=1 sched_yield (Trunk) | 1,441 | 1,553 | 95.52% | 2,116 |
| BG=0 inline (对比) | 1,266 | 1,394 | 95.52% | 0 |

## 轮次记录

### R0: futex + hybrid scaling sweep (2026-08-09)

**futex (方向 D):**
- 1T: agg=1365 (-5.3%) ❌, 16T: agg=3142 (+4.0%) ✅
- CPU -44% 但 wall +5.9%: futex wake 延迟导致 pread 冷读
- 交叉点 ~10-12T

**hybrid pause+yield (方向 B, bonus 发现):**
- 1T: agg=1456 (+1.0%), steady=1627 (**+4.8%**) ✅✅
- 8T: agg=3290 (+0.2%), steady=4089 (+0.2%)
- 16T: agg=3099 (+2.5%), steady=3995 (**+5.1%**) ✅✅
- **全场景正向，是 sched_yield 的严格改进**

**Evidence**: `ndf/evidence/r0-scaling-sweep-20260809.md`

**结论**: 方向 D (futex) 在 1T 证伪，方向 B (hybrid) 全场景帕累托改进。

### R1: io_uring async fadvise (2026-08-09)

**方向 E (io_uring FADVISE):**
- 1T: agg=1272 (-11.7%), 16T: agg=2589 (-14.3%)
- 根因: 异步 fadvise 队列延迟 + SQ 环非线程安全
- **全面证伪**

**Evidence**: `ndf/evidence/r1-iouring-fadvise-20260809.md`

## 总结

| 方案 | 1T steady | 16T steady | 结论 |
|------|----------|-----------|------|
| sched_yield (Trunk) | 1,553 | 3,802 | baseline |
| D: futex | 1,482 (-4.6%) | 3,899 (+2.5%) | 1T 证伪, 16T 小赢 |
| E: io_uring | 1,380 (-11.2%) | 2,954 (-22.3%) | 全面证伪 |
| B: hybrid pause+yield | **1,627 (+4.8%)** | **3,995 (+5.1%)** | **全场景帕累托改进 ✅** |

方向 D + E 证伪。方向 B (hybrid) 是唯一 winner，值得 promote。
