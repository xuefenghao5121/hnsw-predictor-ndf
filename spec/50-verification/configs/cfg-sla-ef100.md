# Config: cfg-sla-ef100

> config_id: cfg-sla-ef100  
> role: CON-GOLDEN A / SLA 基线（保守，recall 优先）  
> aligns: [[CON-SLA-020]], [[CON-GOLDEN-001]]  
> data_path: output/sift1m_m16/sift1m_m16

## Graph / search knobs

| 参数 | 值 |
|------|-----|
| M_graph | 16 |
| REFINE_EF | 100 |
| ADAPTIVE_EF | 0 |
| FLAT_VEC_MB | 64 |

## Shared env (golden common)

```text
CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
FLAT_VEC_MB=64
REFINE_EF=100 ADAPTIVE_EF=0
```

## Protocol

测量口径：[[CON-SLA-014]] strict cgroup + [[CON-SLA-019]] 禁预热 + [[CON-SLA-020]] sustained。
