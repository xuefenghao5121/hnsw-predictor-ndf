# Config: cfg-adaptive-ef90

> config_id: cfg-adaptive-ef90  
> role: CON-GOLDEN B / DEC-086 优化（均衡）  
> aligns: [[DEC-086]], [[CON-GOLDEN-001]]  
> data_path: output/sift1m_m16/sift1m_m16

## Graph / search knobs

| 参数 | 值 |
|------|-----|
| M_graph | 16 |
| REFINE_EF | 90 |
| ADAPTIVE_EF | 1 |
| ADAPTIVE_EASY_EF | 40 |
| ADAPTIVE_EASY_GAP | 1.006 |
| FLAT_VEC_MB | 64 |

## Shared env (golden common)

```text
CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
FLAT_VEC_MB=64
REFINE_EF=90 ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=40 ADAPTIVE_EASY_GAP=1.006
```

## Protocol

测量口径：[[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]] sustained。
