# Proposal: 降 REFINE_EF 减少候选数 {#PROP-REFINE-EF}

> track: poc
> Status: Implemented on 2026-08-03
> 日期: 2026-08-03
> 关联: [[CHR-006]], [[CON-SLA-014]], [[DEC-067]], [[BEH-024]]
> 基线: DEEP10M 2GB cgroup Buffered 1T = 580 QPS, majfault=73005

## 动机

DEEP10M 严格隔离下 majfault=73005，磁盘 I/O 是瓶颈。每次查询 fine rerank 读 ~300 候选 × 4KB 页。
降 REFINE_EF 可直接减少 I/O 量，代价是 recall 下降。

## 探索方向

在 DEEP10M 2GB cgroup 下扫描 REFINE_EF：

| REFINE_EF | 预期候选数 | 预期 I/O 量 | 预期 recall |
|-----------|-----------|------------|------------|
| 300 (当前) | ~300 | ~1.2MB | 95.05% |
| 200 | ~200 | ~0.8MB | ~94%? |
| 150 | ~150 | ~0.6MB | ~93%? |
| 100 | ~100 | ~0.4MB | ~90%? |

目标：找到 recall ≥ 95% 的最低 REFINE_EF，或 recall 仍可接受时最大化 QPS。

## 验证协议

- CON-SLA-014 严格隔离, 2GB cgroup
- flat_vec_cache=128MB, CACHE_MB=128 (已 promote cap fix)
- R0: REFINE_EF=300 (基线)
- R1-R4: REFINE_EF=200/150/100/50

## 非目标

- 不改 PQ 参数（M, nbits）
- 不改搜索算法
- 不改 cgroup 限制
