# Project Genesis ARCHITECTURE (adopt)

> track: bootstrap
> bootstrap_mode: adopt
> status: draft
> source_ref: spec/10-architecture/modules.md
> charter_ref: spec/open/project-genesis/CHARTER.md
> charter_review_sha: 2b7929073114a3949d34c2152b8c7a3ce009642ccd4686d7accd504de9fdbfb7

This file is the Genesis **ARCHITECTURE review** for adopt. Product architecture SoT
remains `spec/10-architecture/`. Core behavior/interfaces SoT remain `spec/20-behavior/`
and `spec/30-interfaces/`. This hop MUST NOT mint new `{#ARCH-*}` / `{#BEH-*}` /
`{#API-*}` clauses, MUST NOT rewrite those trees, and MUST NOT rewrite git history
([[META-009]]).

## Observed modules

From `{#ARCH-001}` / `{#ARCH-003}` (`spec/10-architecture/modules.md`, stable, observed):

| Layer | Modules | Role |
|-------|---------|------|
| L0 data format | `common.h` | binary formats, varint, fvecs IO |
| L1 cache abstraction | `layout_provider.h`, `replacement_policy.h`, `block_heat_evaluator.h` | pluggable layout / replacement |
| L2 cache impl | `block_cache.h/.cpp`, `io_uring_wrapper.h` | BlockCache + io_uring |
| L3 prefetch | `graph_prefetcher.h/.cpp` | graph-guided async prefetch |
| L4 search | `disk_hnsw.h/.cpp` | search + PQ + fine rerank + adjacency |
| L5 application | benchmark, tests, pipeline | consumers |

Pipeline (observed): `build_index` → `extract_graph` → `bfs_reorder` → `write_blocks` /
`write_blocks_veconly` → `train_pq` → `gen_gt`.

`{#ARCH-008}` in this tree is an adopted thin pointer; process body lives in `spec/meta/`.

## Observed core behavior

Inventory only (not rewritten):

| Path | Core IDs (sample) |
|------|-------------------|
| `spec/20-behavior/search.md` | `{#BEH-001}`…`{#BEH-006}`, adjacency / WILLNEED / adaptive EF |
| `spec/20-behavior/cache.md` | `{#BEH-009}`, `{#BEH-010}` |
| `spec/20-behavior/fine-rerank.md` | `{#BEH-007}`, `{#BEH-011}`, `{#BEH-014}` |
| `spec/20-behavior/io-modes.md` | `{#BEH-015}`, `{#BEH-016}` |
| `spec/20-behavior/process.md` | adopted pointers to meta `{#BEH-018}`…`{#BEH-025}` |

Explore-track clauses in `search.md` (`{#BEH-021}`…`{#BEH-023}`, `{#BEH-034}`) stay draft/explore; adopt does not promote them.

## Observed core interfaces

Inventory only (not rewritten):

| Path | Core IDs (sample) |
|------|-------------------|
| `spec/30-interfaces/cxx-api.md` | `{#API-005}`, `{#API-006}` |
| `spec/30-interfaces/cli.md` | `{#API-001}`…`{#API-003}`, `{#API-016}`, `{#API-019}` |
| `spec/30-interfaces/formats.md` | `{#API-004}` |
| `spec/30-interfaces/env.md` | `{#API-007}`…`{#API-013}`, `{#API-017}`, `{#API-018}` |

## Adopt constraints for this ARCHITECTURE

1. Existing `spec/10-architecture/modules.md` is the observed architecture; this review confirms it for Genesis provenance.
2. Existing behavior/interfaces remain product SoT. This hop does not add L0/L1 clauses.
3. Verification / SLA bodies are **not** rewritten in this hop.
4. Trunk `src/` / `include/` / `tests/` are **not** written in this hop.
5. Performance goldens are not minted here; values without evidence stay `draft` / `TBD` / `not-established`.

## Gaps deferred to later Genesis gates

| Later gate | Deferred work |
|------------|----------------|
| `VERIFICATION已审核` | observed `spec/40-constraints/` + `spec/50-verification/` protocol |
| `可以建立初始主线` | Foundation matrix + genesis-pack (adopt does not rebuild Trunk) |
| `GENESIS已审核` | `spec/decisions/dec-project-genesis.md` binding IDEA / NDF SHA / Trunk SHA |

## Gate

ARCHITECTURE 已写好：`spec/open/project-genesis/ARCHITECTURE.md`（产品 SoT 仍为 `spec/10-architecture/modules.md`）。请审阅，回复「ARCHITECTURE已审核」。

MUST NOT write Verification body until that receipt exists in Genesis `GATES.md`.
