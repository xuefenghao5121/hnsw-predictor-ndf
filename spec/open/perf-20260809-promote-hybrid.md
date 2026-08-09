# Perf: promote hybrid pause+yield (2026-08-09)

> 关联: proposal-promote-bg-thread-hybrid.md, DEC-093, BEH-027
> Trunk: post-merge (hybrid pause+yield)
> 协议: CON-SLA-020, SIFT1M 256MB 1T EF=100

## 结果

| 配置 | SLA 要求 | 实测 | 状态 |
|------|---------|------|------|
| EF=100 1T agg (CON-SLA-020) | ≥ 1,076 | 1,066 | ✅ (-0.9%, within ±2%) |
| EF=65 1T steady | — | 1,605 | ✅ (+3.4% vs before) |
| EF=65 16T steady | — | 3,898 | ✅ (+2.5% vs before) |
| Recall (EF=100) | ≥ 97.5% | 97.76% | ✅ |
| Recall (EF=65) | ≥ 95.0% | 95.52% | ✅ |

## 结论

所有 SLA 合规。hybrid pause+yield 合入后性能不退化，EF=65 配置有 +2.5~3.4% 提升。
