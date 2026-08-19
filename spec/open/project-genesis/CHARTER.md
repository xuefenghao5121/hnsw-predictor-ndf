# Project Genesis CHARTER (adopt)

> track: bootstrap
> bootstrap_mode: adopt
> status: draft
> source_ref: spec/00-charter/charter.md
> idea_ref: spec/open/project-genesis/IDEA.md
> idea_review_sha: 99972e9bcb4069364f81f78d727dccc5df7dbb4187d92b020a5d657725642623

This file is the Genesis **CHARTER review** for adopt. Product Charter SoT remains
`spec/00-charter/charter.md`. This hop MUST NOT mint new `{#CHR-*}` clauses, MUST NOT
rewrite the existing Charter tree, and MUST NOT rewrite git history ([[META-009]]).

## Observed goals

From `{#CHR-001}` (stable, observed):

DiskHNSW MUST 在 cgroup 内存限额(≥512MB)下,使用磁盘驻留向量数据,实现与全内存 HNSW
可比的向量搜索召回率(≥95%),同时将常驻内存控制在限额内。

cgroup v2 `memory.max` MUST 同时约束匿名内存与 page cache(file)。

- 优化主目标 ([[DEC-062]]): Buffered（生产默认 `FINE_BUFFERED=1`）。
- 诚实验收地板: O_DIRECT（`FINE_DIRECT=1`）。

IDEA verbatim (already reviewed) remains:

> 在 cgroup 内存限额下，用磁盘驻留向量做接近全内存 HNSW 的召回（≥95%）。

## Observed scope

From `{#CHR-002}`:

- **IN**: L2 向量搜索、PQ 训练与编码、BFS 重排、CSR 邻接表压缩、图引导预取、多线程并发搜索
- **IN**: cgroup 内存受限部署、数据 pipeline 工具链
- **IN**: 可插拔缓存架构（LayoutProvider + ReplacementPolicy）
- **OUT**: 增量插入/删除、多租户 QoS、分布式部署、持久内存
- **OUT**: GPU 加速（P5 规划，非当前 must）

## Observed non-goals

From `{#CHR-003}`:

- 不是通用向量数据库（无 CRUD / WAL）
- 不是实时插入系统（索引构建为离线 batch）
- 不是跨平台方案（Linux 5.1+ io_uring、x86 AVX2 / ARMv9 NEON、C++17）

## Adopt constraints for this CHARTER

1. Existing `spec/00-charter/` is the observed Charter; this review confirms it for Genesis provenance.
2. Existing performance SLA / golden remain product SoT (`spec/40-constraints/`, `{#CHR-006}`). Genesis MUST NOT invent new goldens. Values without new evidence stay `draft` / `TBD` / `not-established`.
3. Architecture, behavior, interfaces, verification bodies are **not** rewritten in this hop.
4. Trunk `src/` / `include/` / `tests/` are **not** written in this hop.
5. Daily Product/Topics remain available; adopt MUST NOT block existing POC work.

## Gaps deferred to later Genesis gates

| Later gate | Deferred work |
|------------|----------------|
| `ARCHITECTURE已审核` | observed `spec/10-architecture/` + core behavior/interfaces inventory |
| `VERIFICATION已审核` | observed `spec/40-constraints/` + `spec/50-verification/` protocol |
| `可以建立初始主线` | Foundation matrix + genesis-pack (adopt does not rebuild Trunk) |
| `GENESIS已审核` | `spec/decisions/dec-project-genesis.md` binding IDEA / NDF SHA / Trunk SHA |

## Gate

CHARTER 已写好：`spec/open/project-genesis/CHARTER.md`（产品 SoT 仍为 `spec/00-charter/charter.md`）。请审阅，回复「CHARTER已审核」。

MUST NOT write Architecture body until that receipt exists in Genesis `GATES.md`.
