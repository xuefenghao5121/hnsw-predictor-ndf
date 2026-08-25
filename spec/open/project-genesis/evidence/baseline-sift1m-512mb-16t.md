# Evidence — sustained baseline reproduce（VER-001）

> hop: genesis_design（continue_baseline）
> date: 2026-08-25
> trunk_sha: d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755
> config: cfg-sla-ef100
> clause: [[VER-001]], [[CON-SLA-001]]

## 场景

SIFT1M（128 维 / 1M），cgroup 512MB，16T，官方 10K query 池，15 轮 × 1000，seed=42，
禁止对被测 query 预热（[[VER-001]]）。

## 复现命令

```bash
CGROUP_MB=512 THREADS=16 bash scripts/run_sustained.sh --config cfg-sla-ef100
```

## 结果（log: `results/sustained/ver043_512mb_16t_n1000_r15.log`）

| 指标 | 值 |
|------|-----|
| agg QPS | 4330.9 |
| Recall@10 | 96.00% |
| steady QPS（Round 15） | 6448.0 |
| Round 1 QPS | 1084.0（ramp-up 494.8%） |
| cumulative unique queries | 7942 / 10000 |
| RSS（anon，峰值） | 352 MB |
| RSS after init | 157 MB |

## cgroup v2 证据（[[VER-003]]）

| 字段 | 值 |
|------|-----|
| `memory.peak` | 536870912 B（= 512 MB） |
| `memory.events.max` | 8368（触顶回收次数） |
| `memory.events.oom` / `oom_kill` | 0 / 0 |
| `memory.stat.file`（残留页缓存） | 165183488 B（~157 MB） |
| `workingset_refault_file` | 455786 |
| `pgmajfault` | 7 |

**判读**：anon RSS 352MB + 页缓存触顶 512MB 预算，内核通过页缓存回收维持运行，全程
`oom=0`。符合 [[CON-001]]（cgroup `memory.max` 约束、`memory.peak`/`memory.stat` 口径）。

## 可复现性

与既有 `results/sustained/official_512mb_16t_n1000_r15.log`（agg 4255.4 QPS / 96.00%
recall）同口径一致（差异 ~1.8% 为运行噪声），确认基线可复现。
