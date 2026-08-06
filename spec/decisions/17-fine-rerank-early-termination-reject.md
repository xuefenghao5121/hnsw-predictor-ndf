# DEC-081: Fine Rerank 早终止在 pread 架构下无效（负结果）

> topic: helmsman-adaptive
> status: rejected
> date: 2026-08-06
> Rejects: helmsman-adaptive (层次 B only)

## 背景

HELMSMAN 提案中层次 B（Fine Rerank 早终止）设想：连续 M 个候选未改善 top-K →
跳过剩余候选的距离计算，减少 Fine Rerank 开销。

## 负结果

### R4: 层次 B 单独验证

| ET 阈值 | Recall | QPS |
|---------|--------|-----|
| 5 | 87.60% | 7,076 |
| 10 | 91.10% | 5,951 |
| 20 | 92.60% | 7,370 |
| 30 | 93.35% | 7,733 |

**全部 recall < 95%，QPS 无收益。**

### R5: A+B 组合

| ET 阈值 | Recall | QPS | vs A-only |
|---------|--------|-----|-----------|
| 20 | 92.80% | 8,785 | worse |
| 50 | 94.60% | 10,210 | -6.9% |

**A+B 叠加全面不如 A 单独。**

## 根因

1. **pread 架构**：先批量读完全部页 → 再逐个算距离。早终止只能省几 ns 的 L2 距离计算，
   不能省已完成的 I/O
2. **SIFT1M 无拐点**：候选 PQ 距离分布无明显"拐点"，连续无改善阈值极难设定
3. **与层次 A 冲突**：A 已减少候选 → B 在已缩减集合上更难触发，引入额外分支开销

## 结论

层次 B 在当前 pread 批量读取架构下**无效**。若未来改为增量 pread（逐候选读），
早终止可能省 I/O，但 syscall 暴增的预期也不乐观。

## 证据

- POC: `poc/helmsman-adaptive/ndf/TOPIC.md` (R4-R5)
- 层次 A promoted 独立 (DEC-080)
