# Decision: Project Genesis accepted (adopt)

> Status: accepted
> track: bootstrap
> bootstrap_mode: adopt
> date: 2026-08-25
> genesis_trunk_sha: d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755
> genesis_ndf_bundle_sha: 59ad73120a745c542ad7a985f3545f92ed1f3539ff027598ec91a5f02f6a6751
> design_completion: spec/open/project-genesis/.ndf-completion/product_proposal-genesis_design-attempt.json
> evidence_bundle_sha: 0201a80884f52039e984e19e3d99358535c2a24ec209fa66f471e84252539419
> roles_sha: 97034c41f33fbc0ef6bcaa60095606b7deb1147c808a47bfc7d19b1fad4f73a4
> perf_status: partial
> depends-on: META-009, META-010

## Summary

Human phrase `GENESIS已审核` freezes Project Genesis for this repo under
`bootstrap_mode=adopt`. NDF kernel was already installed; Command bound kernel
(`FOUNDATION.md`); Control one-shot `hop=genesis_design` wrote draft product NDF
under `spec/00–50`. Existing Trunk at `d0ae5dd` was not rewritten. No
Implementation `genesis-pack` was run (adopt).

## Bindings

| Field | Value |
|-------|-------|
| Trunk SHA | `d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755` |
| Design bundle SHA | `59ad73120a745c542ad7a985f3545f92ed1f3539ff027598ec91a5f02f6a6751` |
| Design hop evidence | `0201a80884f52039e984e19e3d99358535c2a24ec209fa66f471e84252539419` |
| Roles SHA | `97034c41f33fbc0ef6bcaa60095606b7deb1147c808a47bfc7d19b1fad4f73a4` |
| Gate receipt | `spec/open/project-genesis/GATES.md` → `genesis_review` approved |
| Verification ref | `spec/50-verification/verification.md` (draft) |

## Baseline reproduce（2026-08-25，continue_baseline）

Genesis 欠账补测完成：`make test` 构建通过、`test_disk_hnsw` PASS（recall 95.2% vs GT、
100% vs HNSW）；SIFT1M sustained 基线复现（512MB/16T，agg 4330.9 QPS / recall 96.00%），
绑定 `spec/50-verification/baselines/bl-trunk-d0ae5dd.md` + `cfg-sla-ef100`。

非 SLA 骨架（CHR/ARCH/BEH/API/非 SLA CON/VER protocol）晋升 `status=stable`，作为后续
优化（poc/promote）的**对照目标**；SIFT1M sustained 晋升 [[CON-SLA-001]] `status=stable`。

## Known drafts（剩余未确立）

DEEP10M（[[CON-SLA-005]]）、cache-warmed 回归（[[CON-SLA-002]]）、多线程扩展性
（[[CON-SLA-003]]）、I/O 优化收益（[[CON-SLA-004]]）、QPS/MB 内存效率（[[CON-SLA-006]]）
仍 `not-established`；`test_block_cache` / `test_pq_search_quality` 因 fixture/data 缺失
未运行（见 `spec/open/project-genesis/evidence/make-test.md`）。

## Project maturity

`operational`. Further work uses daily tracks (`poc` / `promote` / `bug` / …).
MUST NOT re-run bootstrap for this accepted Genesis.
