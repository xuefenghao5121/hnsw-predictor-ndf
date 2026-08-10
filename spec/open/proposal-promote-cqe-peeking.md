# Promote: CQE Peeking → Fine Rerank io_uring Path
<!-- ndf: kind=proposal status=implementing promotes=ssd-parallelism-io -->
<!-- ndf: source=poc/ssd-parallelism-io/ -->

> Proposal type: promote
> Topic: `poc/ssd-parallelism-io`
> Proposals: `spec/open/proposal-poc-ssd-parallelism-io.md`

## Semantic Core Decision

**Defer** → 行为变更简单（CQE 按完成顺序处理，替代批量屏障），
L3 语义核可在 follow-up product proposal 中补充。
L1 行为 clause (`BEH-036`) + L2 DEC + VER 足够。

## Draft → Stable Clause IDs

| ID | Type | Level | Description |
|----|------|-------|-------------|
| BEH-036 | behavior | 1 | CQE peeking: io_uring fine rerank uses completion-order distance computation |
| API-020 | interface | 2 | FINE_CQE_PEEK env toggle (default 1, 0=legacy batch barrier) |
| DEC-095 | decision | 3 | Promote CQE peeking: +3.5% @1T, +3.2% @4T, thread_local vec_ring_ |

## Key Changes (to merge into Trunk)

### src/core/disk_hnsw.{h,cpp}
1. `vec_ring_` → `static thread_local` (per-thread io_uring, multi-thread safe)
2. Fine rerank io_uring path: batch barrier → CQE peeking with page-to-cands index
3. Lazy init: each thread creates its own io_uring ring on first use
4. `FINE_CQE_PEEK` env toggle (default 1, set to 0 for legacy batch barrier)

### Why this works (from R0-R3 evidence)

| | pread (current) | CQE peeking (proposed) |
|--|:---:|:---:|
| I/O wait | 407us (fixed order blocking) | 256us (completion order, 1st CQE @10us) |
| Submit overhead | 0 (pread syscall) | 79us (io_uring_enter) |
| Net Fine stage | ~414us | ~394us (−5%) |
| **1T QPS** | 1,414.3 | **1,463.1 (+3.5%)** |

R3 confirmed: submit overhead (78us) is irreducible without kernel SQPOLL.
Net benefit = CQE peeking I/O savings − submit overhead > 0.

## Code Merge Plan

Cherry-pick minimal patch from `poc/ssd-parallelism-io/disk_hnsw.cpp` into `src/core/disk_hnsw.cpp`:
- thread_local vec_ring_ declaration + definition
- CQE peeking logic (replace batch barrier block)
- Lazy init wrapper
- FINE_CQE_PEEK env toggle

**No changes to include/, tests/, or other src/ files.** Isolated to fine rerank io_uring path.
