# DEC: Project Genesis {#DEC-PROJECT-GENESIS}

> Status: Accepted
> date: 2026-08-15
> track: bootstrap
> genesis_mode: adopt
> idea_source_ref: spec/open/project-genesis/IDEA.md
> ndf_tree_sha: 5c3dd1d0ca8b179810d9127067a77b1b1c5e9b2f
> genesis_trunk_sha: a14339234133cc6c5a2348464954f744c6465efb
> verification_ref: spec/open/project-genesis/VERIFICATION.md; spec/50-verification/golden-baseline.md; ndf_graphcheck --meta/--product hard_errors=0 (2026-08-15)
> foundation_sha: 0d5781e282a0b99ba3052292faa401b2fc49e7f9acc0eb04fe58aa9e9ab34aaa
> genesis_pack: tmp/genesis-pack-adopt.json
> genesis_pack_manifest_sha: 4cdd72e796d5f6613aad03f3837a593f7cdddbbf64814050d8d274e480afce89
> performance_golden: not-established
> accepted_at: 2026-08-15T14:01:00Z

This decision is **Accepted**. Human phrase `GENESIS已审核` was recorded
2026-08-15T14:01:00Z. The project is `operational`. Bootstrap MUST NOT be re-run;
rebuild the baseline via process/refactor proposals ([[META-009]]).

## Original intent

Verbatim (from `spec/open/project-genesis/IDEA.md`, source `README.md`):

> 在 cgroup 内存限额下，用磁盘驻留向量做接近全内存 HNSW 的召回（≥95%）。

## Accepted goals and non-goals

- Goals: observed [[CHR-001]] — disk-resident vectors, Recall@10 ≥ 95% under cgroup memory limits; Buffered is the optimization target; O_DIRECT is the honest floor.
- Non-goals: observed [[CHR-003]] — not a general vector DB, not online insert, not a portable non-Linux stack.
- Adopt MUST NOT rewrite git history or replace the existing Trunk ([[META-009]]).

## Foundation

- Charter: `spec/00-charter/` (review `spec/open/project-genesis/CHARTER.md`; `charter_review` approved)
- Architecture: `spec/10-architecture/` (review `spec/open/project-genesis/ARCHITECTURE.md`; `architecture_review` approved)
- Behavior / interfaces: `spec/20-behavior/`, `spec/30-interfaces/` (inventoried in ARCHITECTURE)
- Constraints: `spec/40-constraints/` (review `spec/open/project-genesis/VERIFICATION.md`; `verification_review` approved)
- Verification: `spec/50-verification/`
- Foundation matrix: `spec/open/project-genesis/FOUNDATION.md`
- Product Foundation bundle SHA (34 `*.md`, `genesis-pack` `foundation_sha`): `0d5781e282a0b99ba3052292faa401b2fc49e7f9acc0eb04fe58aa9e9ab34aaa`

## Initial Trunk candidate

- Mode: adopt — bind existing Trunk; **no Claude Code write run**
- genesis-pack: `--mode adopt`; `safe_to_dispatch=true`; dispatch skipped because rebuild is forbidden
- Base SHA / candidate commit: `a14339234133cc6c5a2348464954f744c6465efb`
- NDF tree SHA: `git rev-parse HEAD:spec` → `5c3dd1d0ca8b179810d9127067a77b1b1c5e9b2f`
- Build / test evidence: existing product suite + graphcheck hard_errors=0 (meta 0e/1w, product 0e/15w unlinked). Genesis did not re-run Trunk build in this hop.

## Known drafts and debt

- Explore-track product clauses remain draft (e.g. [[BEH-021]], [[BEH-022]], [[BEH-023]], [[BEH-034]], [[CON-SLA-013]]).
- graphcheck product unlinked warnings (API-005/006/007, CHR-002/003, several DEF/CON/VER, DEC-098).
- graphcheck meta unlinked: DEC-HYGIENE-001.
- Daily Product/Topics stay available; rejected topics (e.g. cluster-gbdt / bfs-cluster) are not reopened by this DEC.
- Product performance golden pointer `bl-trunk-golden-7ee4ee2` is **not** a Genesis-minted golden (`performance_golden: not-established`).

## Decision

The bound SHAs resolve (`genesis_trunk_sha` is a commit; `ndf_tree_sha` is `HEAD:spec`).
graphcheck hard_errors=0. `GENESIS已审核` is recorded in Genesis `GATES.md`.
The project is `operational` (adopt). MUST NOT re-run Project Genesis.
