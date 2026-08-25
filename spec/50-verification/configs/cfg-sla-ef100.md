# Config: cfg-sla-ef100

> config_id: cfg-sla-ef100
> role: SLA 基线（保守，recall 优先，EF=100）
> aligns: [[VER-001]], [[CON-SLA-001]]
> data_path: output/sift1m
> vecblocks_path: output/sift1m_vecblocks_64k.bin
> pq_codes_path: output/pqco_sift1m_M32_correct.bin

## Graph / search knobs

| 参数 | 值 |
|------|-----|
| REFINE_EF | 100 |
| ADAPTIVE_EF | 0 |
| FLAT_VEC_MB | 160 |
| CACHE_MB | 64 |

## Shared env（sustained 权威口径）

```text
CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
REFINE_EF=100 ADAPTIVE_EF=0
```

> FLAT_VEC_MB 随 cgroup 预算：`≤256MB → 64`，`512MB → 160`（[[BEH-008]]）。

## Protocol

测量口径：[[VER-001]] sustained 权威口径（官方 10K query 池，15 轮 × 1000，seed=42，
禁止对被测 query 预热）+ [[VER-003]] cgroup v2 隔离（`memory.max=512MB`）。
