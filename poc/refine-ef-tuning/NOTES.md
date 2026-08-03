# POC: Refine EF Tuning

> 提案: `spec/open/proposal-refine-ef.md`（Implemented）
> 基线: DEEP10M 2GB cgroup, Buffered 1T, flat_vec=128MB, CACHE_MB=128

## R0-R4 结果 (2026-08-03, CON-SLA-014, 2GB cgroup, 200q, 1T)

| REFINE_EF | Recall | QPS | RSS | majfault | refault | vs R0 QPS |
|-----------|--------|-----|-----|----------|---------|-----------|
| 300 | **95.05%** | 685 | 1258 | 69075 | 315 | 基线 |
| 200 | **94.25%** | 865 | 1241 | 72791 | 249 | +26% |
| 150 | 93.00% | 1077 | 1228 | 72948 | 222 | +57% |
| 100 | 90.85% | 1315 | 1209 | 72988 | 217 | +92% |
| 50 | 83.20% | 1709 | 1184 | 73584 | 257 | +149% |

### 关键发现

1. **REFINE_EF=200 是最佳平衡点**: Recall=94.25% (仅 -0.8pp), QPS=865 (+26%)
   - 如果 SLA 放宽到 Recall≥94%，REFINE_EF=200 是最优选择
2. **REFINE_EF 与 QPS 近似线性反比**: 300->50 (6x 减少), QPS 685->1709 (2.5x 提升)
3. **majfault 几乎不变** (69K-74K): I/O 次数没减少，但每次 I/O 的等待减少了
   - 原因: fine rerank 候选少了 -> pread 次数少 -> 但 page cache 预算不变 -> 命中率不变
4. **recall 下降是非线性的**: 300->200 只掉 0.8pp, 但 100->50 掉 7.65pp

### 结论

- 当前 SLA (Recall≥95%): REFINE_EF=300 仍是必须的
- 如果愿意放宽到 94%: REFINE_EF=200 可获得 +26% QPS
- PQ 质量改善（减少 false positive）可能允许更低 REFINE_EF 同时保持 recall
- **与 pq-quality POC 互补**: 更好的 PQ -> 更少 false positive -> 更低 REFINE_EF -> 更高 QPS

## 进度

- [x] R0: REFINE_EF=300 (基线)
- [x] R1: REFINE_EF=200
- [x] R2: REFINE_EF=150
- [x] R3: REFINE_EF=100
- [x] R4: REFINE_EF=50
- [ ] 决策: 是否放宽 SLA 到 94% 或等 pq-quality 结果
