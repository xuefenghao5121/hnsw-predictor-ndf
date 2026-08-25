# Project Genesis — Kernel Bind Record

> track: bootstrap
> bootstrap_mode: adopt
> project_maturity: operational
> Status: frozen by GENESIS已审核 2026-08-25

## Kernel

| Field | Value |
|-------|-------|
| `observed_trunk_sha` | d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755 |
| `roles_sha` | 97034c41f33fbc0ef6bcaa60095606b7deb1147c808a47bfc7d19b1fad4f73a4 |
| `bootstrap_mode` | adopt |
| `perf_status` | partial（SIFT1M sustained 已确立；其余 not-established） |
| `genesis_ndf_bundle_sha` | 59ad73120a745c542ad7a985f3545f92ed1f3539ff027598ec91a5f02f6a6751 |

## Product tree

Design hop (`hop=genesis_design`) wrote draft NDF under `spec/00–50` (59 clauses).
See `spec/decisions/dec-project-genesis.md`.

## Trunk observation

Adopt mode: existing DiskHNSW code under `include/` and `src/` is the observed Trunk.
No `genesis-pack` Implementation hop was required.

## Baseline reproduce（2026-08-25）

continue_baseline 完成：SIFT1M sustained 基线复现（512MB/16T，agg 4330.9 QPS / recall
96.00%），绑定 `spec/50-verification/baselines/bl-trunk-d0ae5dd.md`。非 SLA 骨架晋升
`status=stable`，作为优化对照目标。详见 `spec/decisions/dec-project-genesis.md`。

## Gates

`角色已配置` → Command kernel bind → `派发` (design) → **`GENESIS已审核`** (done)
