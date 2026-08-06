# Draft 条款：sustained-query-benchmark

> track: poc
> topic: sustained-query-benchmark
> baseline_trunk_sha: 4a33f38
> 提案: `spec/open/proposal-sustained-query-benchmark.md`

本文件承载本主题的 draft 条款。POC 期间 MUST NOT 写入产品树 `spec/20-behavior/`
或 `spec/30-interfaces/`（[[BEH-018]] 第 6 条、[[CON-POC-001]]）。

---

## 多轮随机采样持续查询基准 {#BEH-035}
<!-- ndf: kind=req level=tbd layer=L1 status=draft since=0.9.10 source=proposed -->
<!-- ndf: topic=sustained-query-benchmark -->

benchmark 工具 SHOULD 支持多轮随机采样模式：从标准 query 池中每轮随机采样
N 个 query，共执行 R 轮，聚合报告总体 QPS 与 recall@k。

### 采样约束

- 采样池 MUST 为**标准 query set**（独立采集），MUST NOT 从 base 抽样
  - rationale: base-sampled query 的 GT top-1 恒为 self（距离 0），recall 虚高 ~10%
- 采样 MUST 由 seed 控制：第 i 轮使用 `seed_base + i`，保证可复现
- 轮内采样 MUST 无放回（同一轮不重复 query）；轮间 MAY 重复
- recall 计算 MUST 基于官方 groundtruth

### 报告约束

- MUST 报告聚合 QPS（总 query 数 / 总耗时）与聚合 recall@k
- SHOULD 报告每轮 QPS，用于观察 page cache 饱和过程
- SHOULD 报告累积 unique query 数，作为 working set 增长的代理指标

### 与单次 benchmark 的关系

R=1 时 MUST 退化为等价于现有单次 benchmark（同 query 集合时结果一致）。

> rationale: 单次固定 query 集会被 page cache 完全吸收（[[DEC-083]]：200q
> working set ~10MB，QPS 高估 2.27–5.43×）。多轮随机采样使累积 working set
> 持续增长，逼近真实生产场景的 I/O 压力。
>
> source: poc/sustained-query-benchmark/ndf/evidence/r0-dataset-verification-20260806.md

---

## 多轮采样 benchmark CLI {#API-019}
<!-- ndf: kind=interface level=tbd layer=L1 status=draft since=0.9.10 source=proposed -->
<!-- ndf: topic=sustained-query-benchmark depends-on=BEH-035 -->

`benchmark_sustained` 命令行接口。

### 位置参数

```
benchmark_sustained <graph> <bfs> <blocks> <route> <data> <query_pool> <gt> <k> <ef>
```

与 `benchmark_diskhnsw`（[[API-002]]）保持一致，除 `<query>` 改为 `<query_pool>`
且 `<num_queries>` 由选项替代。

### 选项

| 选项 | 默认 | 说明 |
|------|------|------|
| `--rounds R` | 10 | 轮数 |
| `--per-round N` | 200 | 每轮采样 query 数 |
| `--seed S` | 42 | 随机种子基值 |
| `--warmup W` | 0 | warmup 轮数（不计入统计） |
| `--verbose` | off | 输出每轮明细 |

### GT 格式

`<gt>` 接受两种格式，按扩展名判定：

| 扩展名 | 格式 |
|--------|------|
| `.ivecs` | 官方格式：每条 `int32 dim` + `dim × int32` |
| `.bin` | 内部格式：`uint32 n` + `uint32 k` + `n×k × uint64` |

### 输出

```
=== Sustained Query Benchmark ===
Pool: 10000 queries | Rounds: 10 | Per-round: 200 | Seed: 42
Round  1: QPS=xxxx  recall=xx.xx%  cumulative_unique=200
...
=== Aggregate ===
Total queries: 2000
Total time:    x.xxx s
QPS:           xxxx
Recall@10:     xx.xx%
Cumulative unique queries: xxxx
```

> rationale: 复用现有 benchmark 位置参数约定降低学习成本；
> GT 双格式支持使官方 `.ivecs` 可直接使用，无需转换。
