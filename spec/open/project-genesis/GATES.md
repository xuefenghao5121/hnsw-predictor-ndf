# Project Genesis Gate Receipts

> append_only: true
> schema: META-010
> track: bootstrap
> bootstrap_mode: adopt

Do not edit or delete old receipts. Append `invalidated` when bound content changes.
File existence is not approval.

| gate | phrase | approved_by | approved_at | approved_content_sha | source_ref | status |
|------|--------|-------------|-------------|----------------------|------------|--------|
| idea_review | IDEA已审核 | human | 2026-08-15T12:52:00Z | 99972e9bcb4069364f81f78d727dccc5df7dbb4187d92b020a5d657725642623 | spec/open/project-genesis/IDEA.md + spec/open/proposal-project-genesis.md | approved |
| charter_review | CHARTER已审核 | human | 2026-08-15T13:14:00Z | 2b7929073114a3949d34c2152b8c7a3ce009642ccd4686d7accd504de9fdbfb7 | spec/open/project-genesis/IDEA.md + spec/open/project-genesis/CHARTER.md | approved |
| architecture_review | ARCHITECTURE已审核 | human | 2026-08-15T13:25:00Z | 77622c30cf5dd8097d1bb3b43c061eeab5f9473570b14bf15837eecd505fb5f2 | spec/open/project-genesis/CHARTER.md + spec/open/project-genesis/ARCHITECTURE.md | approved |
| verification_review | VERIFICATION已审核 | human | 2026-08-15T13:33:00Z | 7db54b0a4f71106a03a6e19f44d1fcf47ae1d92e51976c4229daeeaadf261d8e | spec/open/project-genesis/ARCHITECTURE.md + spec/open/project-genesis/VERIFICATION.md | approved |
| trunk_approval | 可以建立初始主线 | human | 2026-08-15T13:44:00Z | 0d5781e282a0b99ba3052292faa401b2fc49e7f9acc0eb04fe58aa9e9ab34aaa | spec/00-charter/ + spec/10-architecture/ + spec/20-behavior/ + spec/30-interfaces/ + spec/40-constraints/ + spec/50-verification/ (34 *.md) | approved |
| genesis_review | GENESIS已审核 | human | 2026-08-15T14:01:00Z | 3164f8cf3aff8bfd53b27b1a8dd49911013deb2e10a626460ea34c2732f79338 | spec/decisions/dec-project-genesis.md + spec/open/project-genesis/VERIFICATION.md | approved |

## Canonical bundles

- `idea_review`: IDEA + bootstrap proposal (`legacy_whole_file`)
- `charter_review`: IDEA + Charter
- `architecture_review`: Charter + Architecture + core behavior/interfaces
- `verification_review`: constraints + verification protocol
- `trunk_approval`: all Foundation artifacts
- `genesis_review`: Genesis DEC + NDF tree SHA + Trunk SHA + verification evidence

## Receipt notes

- **2026-08-15T12:52:00Z**: Human phrase `IDEA已审核` received in Composer. `idea_review` recorded `approved`. Bundle SHA is `sha256(sorted(repo-relative path + NUL + file bytes + NUL))` over `spec/open/project-genesis/IDEA.md` and `spec/open/proposal-project-genesis.md`. Those two files were not modified after the phrase.
- `approved_by=human` copies the Composer speaker of the exact phrase. Agent names were not used.
- After the IDEA receipt, Charter review was drafted at `spec/open/project-genesis/CHARTER.md`. Product SoT remains `spec/00-charter/`.
- **2026-08-15T13:14:00Z**: Human phrase `CHARTER已审核` received in Composer. `charter_review` recorded `approved`. Bundle SHA is `legacy_whole_file` over `spec/open/project-genesis/IDEA.md` and `spec/open/project-genesis/CHARTER.md`. Those two files were not modified after the phrase.
- After the CHARTER receipt, Architecture review was drafted at `spec/open/project-genesis/ARCHITECTURE.md`. Product SoT remains `spec/10-architecture/`.
- **2026-08-15T13:25:00Z**: Human phrase `ARCHITECTURE已审核` received in Composer. `architecture_review` recorded `approved`. Bundle SHA is `legacy_whole_file` over `spec/open/project-genesis/CHARTER.md` and `spec/open/project-genesis/ARCHITECTURE.md` (the review packet presented for this gate; product behavior/interfaces remain inventoried inside ARCHITECTURE.md). Those two files were not modified after the phrase.
- After the ARCHITECTURE receipt, Verification review was drafted at `spec/open/project-genesis/VERIFICATION.md`. Product SoT remains `spec/40-constraints/` and `spec/50-verification/`.
- **2026-08-15T13:33:00Z**: Human phrase `VERIFICATION已审核` received in Composer. `verification_review` recorded `approved`. Bundle SHA is `legacy_whole_file` over `spec/open/project-genesis/ARCHITECTURE.md` and `spec/open/project-genesis/VERIFICATION.md`. Those two files were not modified after the phrase.
- After the VERIFICATION receipt, Foundation matrix was drafted at `spec/open/project-genesis/FOUNDATION.md`.
- **2026-08-15T13:44:00Z**: Human phrase `可以建立初始主线` received in Composer. `trunk_approval` recorded `approved`. Bundle SHA is `legacy_whole_file` over all `spec/{00-charter,10-architecture,20-behavior,30-interfaces,40-constraints,50-verification}/**/*.md` (34 files), matching `genesis-pack` `foundation_sha`. Those product files were not modified after the phrase. Adopt binds existing Trunk `a14339234133cc6c5a2348464954f744c6465efb`; Claude Code is **not** dispatched to rebuild `src/`.
- After trunk approval: `genesis-pack --mode adopt` (`foundation_sha` match, `safe_to_dispatch=true`, dispatch skipped). Proposed Genesis DEC written at `spec/decisions/dec-project-genesis.md`.
- **2026-08-15T14:01:00Z**: Human phrase `GENESIS已审核` received in Composer. DEC Status stamped `Accepted` / `accepted_at=2026-08-15T14:01:00Z` (gate effect authorized by the phrase; goals/Foundation/Trunk body otherwise unchanged). `genesis_review` recorded `approved`. Bundle SHA is `legacy_whole_file` over `spec/decisions/dec-project-genesis.md` and `spec/open/project-genesis/VERIFICATION.md`. Bound `genesis_trunk_sha=a14339234133cc6c5a2348464954f744c6465efb` resolves. Project is `operational`. MUST NOT re-run bootstrap.
