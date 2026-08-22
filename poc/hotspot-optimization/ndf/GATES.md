# GATES — hotspot-optimization

> topic_id: hotspot-optimization
> append_only: true
> schema: META-010

Do not infer approval from file existence. Do not rewrite old receipts; append `invalidated`.

| Gate | Phrase | State | approved_by | approved_content_sha | bundle_mode |
|------|--------|-------|-------------|----------------------|-------------|
| topic_review | TOPIC已审核 | pending | | | |
| design_review | DESIGN已审核 | blocked_by_binder | | | |
| implementation_approval | 可以开始实现 | blocked_by_binder | | | |

Product proposal: 已确认 (received) → 已审核 (received 2026-08-18). 已审核 is not TOPIC已审核.

## Canonical bundles

- `topic_review`: `TOPIC.md` + root proposal `spec/open/proposal-poc-hotspot-optimization.md`
- `design_review`: `TOPIC.md` + `DESIGN.md`
- `implementation_approval`: `TOPIC.md` + `DESIGN.md` + PERF_BASELINE bind header + DELTA hypothesis + `INTERFACE.md`

## Gate 1/3 topic_review — CONFIRMED (2026-08-18T16:34Z)

> pipeline: gate | episode: ep-gate-topic-review-hotspot-optimization-20260818T163400Z
> manifest_sha: f25c728fba115e17ed5421d4c7fc940f16ff173ae691245a076e6a9913f5661e
> context_plan_sha: aefcb8433f168908a23427fa53603bfe1ccc582a07fe3a438424e07d8c4cf2cc

- Human phrase `TOPIC已审核` received in Composer.
- `approved_content_sha` copied verbatim from control-pack `gates.topic_review.expected_content_sha`.
- `bundle_mode`: `legacy_whole_file`
- `slice_manifest_sha`: (none)
- `approved_by`: human
- Bundle paths unchanged since pack compilation: `poc/hotspot-optimization/ndf/TOPIC.md` + `spec/open/proposal-poc-hotspot-optimization.md`.
- MUST NOT treat this as DESIGN已审核. DESIGN.md was missing at confirmation time.

| gate | phrase | approved_by | approved_at | approved_content_sha | bundle_mode | slice_manifest_sha | source_ref | status |
|------|--------|-------------|-------------|----------------------|-------------|-------------------|------------|--------|
| topic_review | TOPIC已审核 | human | 2026-08-18T16:34:00Z | 8b7505e875167dc2710dd5e26d880395985be25892cb7953523d484d7a397707 | legacy_whole_file | | poc/hotspot-optimization/ndf/TOPIC.md + spec/open/proposal-poc-hotspot-optimization.md | approved |

## Gate 2/3 design_review — pending (DESIGN.md drafted 2026-08-18T16:36Z)

- Binder facet `DESIGN.md` now exists. `approved_by` and `approved_content_sha` remain empty.
- This is not DESIGN已审核. Next human phrase: `DESIGN已审核`.

| gate | phrase | approved_by | approved_at | approved_content_sha | bundle_mode | slice_manifest_sha | source_ref | status |
|------|--------|-------------|-------------|----------------------|-------------|-------------------|------------|--------|
| design_review | DESIGN已审核 | | | | | | poc/hotspot-optimization/ndf/TOPIC.md + poc/hotspot-optimization/ndf/DESIGN.md | pending |

## Gate 1/3 topic_review — review_slice rebind (2026-08-18T17:59Z)

> pipeline: gate | episode: ep-gate-design-review-hotspot-optimization-20260818T175900Z
> manifest_sha: 2a036bb5e6e8bca0875ade54af690aca79ccabdfeb4c589c7c04d99cc35c9887
> context_plan_sha: 72bf2d35060382ba5ef15202ba9532f27bef77759e9e008a3920aaa2cd9b60c7

- DESIGN.md already contained `design_contract` markers, so the pack flipped all gates to `review_slice`.
- Mechanical `topic_contract` / `proposal_contract` markers were added; Active Hypothesis and proposal contract prose were not rewritten.
- Old 2026-08-18T16:34Z row is not rewritten. Append `invalidated` for `legacy_whole_file` vs current `review_slice`.
- Rebind uses the same human phrase `TOPIC已审核` (2026-08-18T16:34:00Z). MUST NOT ask the human to re-say it.
- `approved_content_sha` copied verbatim from control-pack `gates.topic_review.expected_content_sha`.

| gate | phrase | approved_by | approved_at | approved_content_sha | bundle_mode | slice_manifest_sha | source_ref | status |
|------|--------|-------------|-------------|----------------------|-------------|-------------------|------------|--------|
| topic_review | TOPIC已审核 | openclaw-audit | 2026-08-18T17:59:00Z | 8b7505e875167dc2710dd5e26d880395985be25892cb7953523d484d7a397707 | legacy_whole_file | | poc/hotspot-optimization/ndf/TOPIC.md + spec/open/proposal-poc-hotspot-optimization.md | invalidated |
| topic_review | TOPIC已审核 | human | 2026-08-18T16:34:00Z | bb89e6e809770240703f9285d541a1ca3d00cd0cf6cf4a4329e2381aa03a61f0 | review_slice | 33a03f685c0998ef1db23f9ccb99951da2313174e0e8e433d86ea875be281a26 | poc/hotspot-optimization/ndf/TOPIC.md + spec/open/proposal-poc-hotspot-optimization.md | approved |

## Gate 2/3 design_review — CONFIRMED (2026-08-18T17:59Z)

> pipeline: gate | episode: ep-gate-design-review-hotspot-optimization-20260818T175900Z
> manifest_sha: 2a036bb5e6e8bca0875ade54af690aca79ccabdfeb4c589c7c04d99cc35c9887
> context_plan_sha: 72bf2d35060382ba5ef15202ba9532f27bef77759e9e008a3920aaa2cd9b60c7

- Human phrase `DESIGN已审核` received in Composer.
- `approved_content_sha` copied verbatim from control-pack `gates.design_review.expected_content_sha`.
- `bundle_mode`: `review_slice`
- `slice_manifest_sha`: `2c34dd7b5a5898bbf359ccf8e02d52715349183750eee35d4669339d6dd89c8d`
- `approved_by`: human
- Bundle: `topic_contract` + `design_contract` (`DESIGN.md` contract SHA unchanged: `f624782e72e8439f8330c07af137e8f52b43523156c98668dcfb2e93f0575a48`).
- MUST NOT treat this as `可以开始实现`. MUST NOT write topic code this hop.

| gate | phrase | approved_by | approved_at | approved_content_sha | bundle_mode | slice_manifest_sha | source_ref | status |
|------|--------|-------------|-------------|----------------------|-------------|-------------------|------------|--------|
| design_review | DESIGN已审核 | human | 2026-08-18T17:59:00Z | ae81e56722dcd7543e029fa61ba2df578ae06f56485248d3e4f9d2b585deba6e | review_slice | 2c34dd7b5a5898bbf359ccf8e02d52715349183750eee35d4669339d6dd89c8d | poc/hotspot-optimization/ndf/TOPIC.md + poc/hotspot-optimization/ndf/DESIGN.md | approved |

## Gate 3/3 implementation_approval — pending (binder facets 2026-08-18T17:59Z)

- PERF_BASELINE bind header, DELTA hypothesis, and INTERFACE now exist.
- `approved_by` and `approved_content_sha` remain empty.
- This is not `可以开始实现`. Next human phrase: `可以开始实现`.
- MUST NOT write topic code until that phrase and a matching receipt SHA.

| gate | phrase | approved_by | approved_at | approved_content_sha | bundle_mode | slice_manifest_sha | source_ref | status |
|------|--------|-------------|-------------|----------------------|-------------|-------------------|------------|--------|
| implementation_approval | 可以开始实现 | | | | | | TOPIC+DESIGN+PERF_BASELINE+DELTA+INTERFACE | pending |

## Gate 3/3 implementation_approval — CONFIRMED (2026-08-18T18:06Z)

> pipeline: gate | episode: ep-gate-impl-approval-hotspot-optimization-20260818T180600Z
> manifest_sha: ea5e33ee8aa7d54c5e287c10d51a0f95d1ef6f91b71b0648a3bcf4c8c92eb199
> context_plan_sha: a0f9ecd017f7fbf4002e8ad550d654e2269bf875a5cc32c1c8bdda034d39d33a

- Human phrase `可以开始实现` received in Composer.
- `approved_content_sha` copied verbatim from control-pack `gates.implementation_approval.expected_content_sha`.
- `bundle_mode`: `review_slice`
- `slice_manifest_sha`: `0db072d5179f1965807140f3992b7fbf282fca54b627829fc8913b82e7684fc5`
- `approved_by`: human
- This phrase permits POC code under `poc/hotspot-optimization/` only. MUST NOT write Trunk `src/` / `include/` / `tests/`.
- This is not a close/promote decision.

| gate | phrase | approved_by | approved_at | approved_content_sha | bundle_mode | slice_manifest_sha | source_ref | status |
|------|--------|-------------|-------------|----------------------|-------------|-------------------|------------|--------|
| implementation_approval | 可以开始实现 | human | 2026-08-18T18:06:00Z | 777532b1417e70dbcae05e6d016443c04dd9eb4ae948de917443038c43c4a80b | review_slice | 0db072d5179f1965807140f3992b7fbf282fca54b627829fc8913b82e7684fc5 | TOPIC+DESIGN+PERF_BASELINE+DELTA+INTERFACE | approved |
