# Project Genesis IDEA

> track: bootstrap
> bootstrap_mode: adopt
> status: draft
> project_maturity: operational_legacy
> source_ref: README.md; spec/00-charter/charter.md {#CHR-001}

## Verbatim idea

Observed product wording (not paraphrased; not invented in this hop):

> 在 cgroup 内存限额下，用磁盘驻留向量做接近全内存 HNSW 的召回（≥95%）。

Source: `README.md` (repository one-liner).

Charter observed wording (`spec/00-charter/charter.md` {#CHR-001}):

> DiskHNSW MUST 在 cgroup 内存限额(≥512MB)下,使用磁盘驻留向量数据,实现与全内存 HNSW 可比的向量搜索召回率(≥95%),同时将常驻内存控制在限额内。

This hop did not receive a new user-authored IDEA. Canvas action `new-genesis` is an adopt of the existing DiskHNSW / `hnsw-predictor-ndf` tree to backfill Project Genesis provenance ([[META-009]]).

## Problem and target user

- Problem (observed): traditional in-memory HNSW keeps all vectors resident; hnswlib needs ~726MB RSS for SIFT1M and ~7GB for DEEP10M, which is infeasible under container/cgroup memory limits.
- Target user (observed from Charter/README): operators running vector search under cgroup v2 `memory.max` (typical ≥512MB).
- Existing alternative (observed): hnswlib full-memory HNSW.

Deductions (not user statements): this is a healthy brownfield (`operational_legacy`) with existing `spec/00–50`, Trunk `src/`, and 130 product clauses. Adopt records Genesis provenance; it MUST NOT rewrite git history or re-author Foundation in this stage.

## Goals

1. Preserve the observed product goal: disk-resident vectors, Recall@10 ≥ 95% under cgroup memory limits.
2. Backfill Project Genesis artifacts so Control can bind IDEA → Foundation → Trunk SHA without claiming a new product.
3. Keep daily Product/Topics available; adopt MUST NOT block existing POC work.

## Non-goals

1. MUST NOT re-run as greenfield or replace the existing Trunk.
2. MUST NOT write or rewrite L0/L1 Foundation, `src/`, `include/`, or `tests/` in the IDEA stage.
3. MUST NOT invent new performance goldens; existing SLA/golden remain product SoT. New values without evidence stay `draft` / `TBD` / `not-established`.
4. MUST NOT rewrite existing git history (adopt rule, [[META-009]]).

## Success conditions

| Condition | Measure | Status |
|-----------|---------|--------|
| IDEA preserved with source_ref | this file + bootstrap proposal | draft |
| Human `IDEA已审核` receipt | Genesis `GATES.md` (not yet written) | pending |
| Adopt does not rewrite history | no history rewrite in later gates | draft |
| Existing Charter/Trunk remain observed inputs | `spec/00-charter/`, `src/` | observed |

## Failure / stop conditions

- User declines adopt; leave `operational_legacy` without Genesis decision.
- Accepted Genesis already exists (would be a stop; not the case here: `accepted=false`).
- Request to rewrite Trunk history or mint unearned performance goldens.

## Hard constraints

- Platform: Linux 5.1+ (io_uring), x86_64 AVX2 / ARMv9 NEON (observed)
- Language/runtime: C++17 Trunk; Python for bench/pipeline/meta tools (observed)
- Resources: cgroup v2 `memory.max` typical ≥512MB; page cache shares the budget (observed {#CHR-001})
- Compliance: NDF dual-track [[CHR-008]]; adopt MUST NOT silently approve gates ([[META-010]])

## Unknowns requiring POC

- Not in this hop. Existing exploring/closed topics stay on Product/Topics; Genesis adopt does not open a product POC.

## Gate

Do not generate Charter/Architecture bodies until `IDEA已审核` has a valid receipt in Genesis
`GATES.md`.
