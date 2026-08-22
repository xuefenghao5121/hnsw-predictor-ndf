# Config: cfg-m24-ef60

> config_id: cfg-m24-ef60  
> role: CON-GOLDEN C / DEC-087 Pareto（激进，QPS 优先）  
> aligns: [[DEC-087]], [[CON-GOLDEN-001]]  
> data_path: output/sift1m_m24/sift1m_m24
> vecblocks_path: output/sift1m_m24/sift1m_m24_vecblocks_64k_cluster1024.bin
> cluster_sort: BEH-037 (k=1024, promoted)
> cluster_k: 1024
> cluster_input: output/sift1m_m24/sift1m_m24_vecblocks_64k.bin

## Graph / search knobs

| 参数 | 值 |
|------|-----|
| M_graph | 24 |
| REFINE_EF | 60 |
| ADAPTIVE_EF | 0 |
| FLAT_VEC_MB | 64 |

## Shared env (golden common)

```text
CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
FLAT_VEC_MB=64
REFINE_EF=60 ADAPTIVE_EF=0
```

## Protocol

测量口径：[[CON-SLA-014]] + [[CON-SLA-019]] + [[CON-SLA-020]] sustained。
