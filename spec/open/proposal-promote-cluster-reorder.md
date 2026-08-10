# Promote: Vecblock Cluster Reorder (BEH-037)
<!-- ndf: kind=proposal status=implementing promotes=vecblock-cluster-reorder -->
<!-- ndf: source=poc/vecblock-cluster-reorder/ -->

> Proposal type: promote
> Topic: `poc/vecblock-cluster-reorder`
> Target: offline tool (no Trunk search code changes)

## Semantic Core Decision

**Defer** → 离线 vecblock 重写工具，不修改搜索代码路径。
L3 语义核可在后续 product proposal 中补充。
L1 behavior clause (BEH-037) + L2 API (API-021) + DEC-096 足够。

## Draft → Stable Clause IDs

| ID | Type | Level | Description |
|----|------|-------|-------------|
| BEH-037 | behavior | 1 | Cluster-sorted vecblock layout improves I/O locality |
| API-021 | interface | 2 | cluster_reorder tool + VECBLOCK_CLUSTER_K env |
| DEC-096 | decision | 3 | Promote within-block cluster sort k=1024 |

## What Gets Promoted

### src/pipeline/cluster_reorder.cpp
- Read existing vecblocks → k-means cluster → within-block cluster sort → write new vecblock
- Offline tool, no runtime dependency in search path
- Build: `make cluster_reorder`

### No Trunk search code changes
- vecblock format unchanged → DiskHNSW reads cluster-sorted file as-is
- Route table unchanged (block boundaries preserved)
- Hot-swap: replace vecblock file, restart benchmark

## Evidence (R0, R2)

| Scene | BFS baseline | Cluster k=1024 | Delta |
|------|:---:|:---:|:---:|
| 256MB 1T | 1,438 | 1,775 | **+23.4%** |
| 256MB 16T | 3,483 | 5,253 | **+50.8%** |
| 512MB 1T | — | 2,198 | — |
| 512MB 16T | — | 8,987 | — |

Profile (CQE, 1T): io_rest 242→144us (−40%)
Full reorder (R1) ruled out: −1.5% (destroys BFS locality)
