# R1+R2: Incremental Pread + Early Stop Results

> date: 2026-08-09
> topic: fine-rerank-incremental
> protocol: CON-SLA-014 + CON-SLA-019 + CON-SLA-020 (sustained, N=1000 R=15 seed=42)

## 配置

M=16 EF=65, 256MB cgroup, 1T, 全部同日背靠背执行。

## 结果

| 配置 | Agg QPS | Steady QPS | Recall (agg) | vs R0 | Recall ≥95%? |
|------|---------|-----------|-------------|-------|-------------|
| **R0 baseline (Trunk)** | **1,480.3** | **1,657.8** | **95.52%** | — | ✅ |
| R1 inc B=16 no-stop | 1,460.7 | 1,604.5 | 95.52% | -1.3% | ✅ |
| R2 B=8 early-stop | 1,512.2 | 1,666.9 | **94.51%** | +2.2% | ❌ |
| R2 B=16 early-stop (margin) | 1,487.4 | 1,657.2 | 95.28% | +0.5% | ✅ |
| R2 B=16 streak=10 | 1,494.3 | 1,673.1 | 95.28% | +0.9% | ✅ |
| R2 B=16 streak=20 | 1,492.4 | 1,658.9 | 95.28% | +0.8% | ✅ |

## 分析

### 1. 增量架构本身不退化 ✅
R1（增量 pread，无早终止）vs R0：agg -1.3%，steady -3.2%，recall 完全一致。
差异在噪声范围内，验证了增量 pread 的正确性。

### 2. 早终止收益微小 ⚠️
- B=16 early-stop: agg +0.5~0.9%，recall -0.24pp（95.52% → 95.28%）
- Steady QPS 几乎不变（1,657 vs 1,658），说明 I/O 节省被 batch 开销抵消

### 3. B=8 太激进 ❌
recall 94.51% < 95%，SLA 不达标。小 batch 下早终止触发频率高但裁剪过度。

### 4. Streak 参数影响微弱
s0/s10/s20 结果几乎一致，说明早终止主要靠 margin 条件（batch_hits==0 && processed>=2k）触发，
streak 条件几乎不被激活。

### 5. 与 DEC-081 一致
DEC-081 结论：「SIFT1M 候选 PQ 距离分布无明显"拐点"」。
R2 再次验证：即使改为增量读取（省 I/O 而非省计算），早终止仍无法有效触发。
根因是 SIFT1M 的候选质量分布平坦，前 k 个候选与后续候选的 PQ 距离差异极小。

## 根因

SIFT1M M=16 EF=65 下：
- ~65 候选中 ~30-40 需要 I/O（50% cache 命中）
- 候选按 PQ 距离升序，但分布平坦（无明显拐点）
- 前 16 个候选中大概率有多个进入 top-K（batch_hits > 0），margin 条件不触发
- 即使触发，仅省 ~15-20 个 pread（剩余候选的 I/O），而 batch 边界引入额外开销

## 结论

**Fine Rerank 增量早终止在 SIFT1M M=16 EF=65 256MB 1T 下无显著收益。**

方向与 DEC-081 一致，根因相同（PQ 距离分布无拐点），只是换了一种"省 I/O"的角度仍然无效。

> source: poc/fine-rerank-incremental/results/r1_inc_b16_nostop.log ; r2_b*.log
