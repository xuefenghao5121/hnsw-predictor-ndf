# Project Genesis Gate Receipts

> append_only: true
> schema: META-010
> bootstrap_mode: adopt
> genesis_shape: kernel_bind_design_hop

Do not infer approval from file existence alone.

| gate | phrase | approved_by | approved_at | approved_content_sha | source_ref | status |
|------|--------|-------------|-------------|----------------------|------------|--------|
| roles_bound | 角色已配置 | human | 2026-08-24T15:47:54Z | 97034c41f33fbc0ef6bcaa60095606b7deb1147c808a47bfc7d19b1fad4f73a4 | ndf.workflow.yaml roles | approved |
| genesis_review | GENESIS已审核 | human | 2026-08-25T06:37:32Z | 59ad73120a745c542ad7a985f3545f92ed1f3539ff027598ec91a5f02f6a6751 | design hop changed_files bundle + FOUNDATION | approved |

## Canonical bundles

- `roles_bound`: `ndf.workflow.yaml` roles 段
- `genesis_review`: `genesis_design` completion `changed_files` whole-file bundle
  (`spec/00-charter/charter.md` … `spec/50-verification/verification.md`,
  `spec/decisions/dec-adopt-and-measurement.md`, `spec/INDEX.md`)

## Notes

- Prior legacy Foundation drafts (IDEA/CHARTER/ARCHITECTURE) voided per [[META-010]] §7 before GENESIS freeze.
- **2026-08-24T22:36:00Z**: Command kernel re-bind after process land `proposal-meta-genesis-kernel-bind`.
- **2026-08-24T19:42Z–19:55Z**: Human「派发」→ Control `hop=genesis_design` succeeded; disk
  `ndf-agent-completion/v1` at
  `spec/open/project-genesis/.ndf-completion/product_proposal-genesis_design-attempt.json`
  (`evidence_bundle_sha=0201a808…`).
- **2026-08-25T06:37:32Z**: Human phrase `GENESIS已审核` in Composer. `genesis_review`
  recorded `approved`. Bundle SHA is `legacy_whole_file` =
  `sha256(sorted(repo-relative path + NUL + file bytes + NUL))` over the eight
  design-hop `changed_files`. `approved_by=human` copies the Composer speaker.
  adopt mode: no Implementation `genesis-pack`. Project enters **operational**.
