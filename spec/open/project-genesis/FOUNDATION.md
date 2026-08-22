# Project Genesis Foundation Matrix

> track: bootstrap
> bootstrap_mode: adopt
> project_maturity: operational
> next_gate: none (GENESIS已审核)
> observed_trunk_sha: a14339234133cc6c5a2348464954f744c6465efb
> verification_review_sha: 7db54b0a4f71106a03a6e19f44d1fcf47ae1d92e51976c4229daeeaadf261d8e

Adopt inventory. Product SoT remains `spec/00–50`. This matrix MUST NOT rewrite L0/L1,
MUST NOT rewrite git history, and MUST NOT mint new performance goldens ([[META-009]]).
`genesis-status` MAY report `trunk_candidate` after this file exists because Trunk `src/`
already exists; that is observed brownfield, not a new slice.

## Design space

| Artifact | Path | Status | Gate SHA | Gaps |
|----------|------|--------|----------|------|
| Charter | `spec/00-charter/` + `spec/open/project-genesis/CHARTER.md` | observed | `2b7929073114a3949d34c2152b8c7a3ce009642ccd4686d7accd504de9fdbfb7` | none for adopt provenance |
| Architecture | `spec/10-architecture/` + `spec/open/project-genesis/ARCHITECTURE.md` | observed | `77622c30cf5dd8097d1bb3b43c061eeab5f9473570b14bf15837eecd505fb5f2` | none for adopt provenance |
| Behavior | `spec/20-behavior/` | observed | inventoried in ARCHITECTURE | explore-track clauses stay draft |
| Interfaces | `spec/30-interfaces/` | observed | inventoried in ARCHITECTURE | none for adopt provenance |

## Implementation space

| Slice | Target paths | Depends on clauses | Candidate status |
|-------|--------------|--------------------|------------------|
| existing Trunk (adopt) | `src/`, `include/`, `tests/` | `{#CHR-001}`, `{#ARCH-003}`, `{#API-005}` | observed-existing at `a14339234133cc6c5a2348464954f744c6465efb` |

Adopt MUST NOT create a replacement vertical slice or rewrite history. Unknown
mechanisms stay later POCs. genesis-pack waits for `可以建立初始主线`.

## Test space

| Contract | Verification path | Baseline | Status |
|----------|-------------------|----------|--------|
| minimum functional acceptance | `spec/50-verification/acceptance.md` `{#VER-001}`… | product suite | observed |
| honest / cgroup protocol | `spec/40-constraints/sla.md` `{#CON-SLA-014}` `{#CON-HONEST-002}` | product SLA | observed |
| performance Golden Baseline | `spec/50-verification/golden-baseline.md` → `bl-trunk-golden-7ee4ee2` | product golden (not Genesis-minted) | observed pointer |

Genesis does not re-measure in this hop. New values without evidence stay `draft` /
`TBD` / `not-established`. Project-goal goldens ≠ performance goldens.

## Initial traceability

| Goal / clause | Design | Implementation slice | Verification | Gap |
|---------------|--------|----------------------|--------------|-----|
| `{#CHR-001}` disk HNSW under cgroup | `spec/00-charter/charter.md` | `src/core/disk_hnsw.cpp` | `{#VER-003}` / `{#CON-SLA-020}` | none for provenance |
| `{#ARCH-003}` module layers | `spec/10-architecture/modules.md` | `include/` + `src/core/` | `{#VER-001}` | none for provenance |
| `{#CON-SLA-014}` strict isolation | `spec/40-constraints/sla.md` | test infra / cgroup scripts | `{#VER-039}` | none for provenance |
| `{#CON-GOLDEN-001}` golden config | `spec/40-constraints/sla.md` | Trunk at observed SHA | `golden-baseline.md` | Genesis freeze still pending |

## Gates

`CHARTER已审核` → `ARCHITECTURE已审核` → `VERIFICATION已审核` →
`可以建立初始主线`.

Foundation 已写好：`spec/open/project-genesis/FOUNDATION.md`。请决定是否绑定现有 Trunk 为 Genesis candidate，回复「可以建立初始主线」。

MUST NOT dispatch `genesis-pack` or write `spec/decisions/dec-project-genesis.md` until that receipt exists in Genesis `GATES.md`.
