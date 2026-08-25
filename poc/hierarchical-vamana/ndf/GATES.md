# POC Gate Receipts

> topic_id: hierarchical-vamana
> append_only: true
> schema: META-010
> bundle_mode: review_slice
> path: text_first

Do not infer approval from file existence. Do not rewrite old receipts; append `invalidated`.

| gate | phrase | approved_by | approved_at | approved_content_sha | source_ref | status | bundle_mode | slice_manifest_sha |
|------|--------|-------------|-------------|----------------------|------------|--------|-------------|--------------------|
| topic_review | TOPIC已审核 | | | | | pending | review_slice | |
| design_review | DESIGN已审核 | | | | | pending | review_slice | |
| implementation_approval | 可以开始实现 | | | | | pending | review_slice | |
| bundle_dispatch | 派发 | human | 2026-08-25T10:41:39Z | ef63b81a35055dcf7022e22af89a612f283193e545ef21ba488e3ed11b02e1f2 | TOPIC+DESIGN+PERF_BASELINE+DELTA+INTERFACE | invalidated | review_slice | 3fc4a2e4e81d7063d57b6f3ae95b55e1c3d91d2543e1037e61b56165633725c7 |
| bundle_dispatch | 派发 | human | 2026-08-25T12:07:55Z | c4c9a2f0d708bd3d214c7ecaff2687b8fda0fdbf68af517766db7bb3bb6529b9 | TOPIC+DESIGN+PERF_BASELINE+DELTA+INTERFACE | invalidated | review_slice | 24040a54ba37060c582bce435426f71b654c57c149eac973f9041b1afa463706 |
| bundle_dispatch | 派发 | human | 2026-08-25T12:31:03Z | c4c9a2f0d708bd3d214c7ecaff2687b8fda0fdbf68af517766db7bb3bb6529b9 | TOPIC+DESIGN+PERF_BASELINE+DELTA+INTERFACE | invalidated | review_slice | 24040a54ba37060c582bce435426f71b654c57c149eac973f9041b1afa463706 |
| bundle_dispatch | 派发 | human | 2026-08-25T15:06:47Z | 3244a5ceced403df486de7c3c45e1f3ee808389691328fd33214e33896fdbd64 | TOPIC+DESIGN+PERF_BASELINE+DELTA+INTERFACE | approved | review_slice | 20bb9e61cf99ce00a0f20b60b55c2a640720664e6a601ca47137917d3366aa75 |

## Canonical review slices

- `topic_review`: `topic_contract` (+ proposal when present)
- `design_review`: `topic_contract` + `design_contract`
- `implementation_approval` / `bundle_dispatch`: `topic_contract` + `design_contract` +
  `perf_bind` + `delta_hypothesis` + `interface_contract`

`PERF_BASELINE Numbers`, `DELTA Rounds`, evidence, COMMITS and this GATES file are mutable
outside review slices and do not change gate SHA.

## Notes

- Human phrase `派发` (text-first) recorded on 2026-08-25T10:41:39Z; binds implementation license via
  `bundle_dispatch` (same review-slice SHA as `implementation_approval`).

- Human phrase `派发` (text-first) recorded at 2026-08-25T12:07:55Z; rebinds after R0 delta_hypothesis status drift. R1 measure: α sweep @ 16T (tmp/intent-hierarchical-vamana-measure-r1.md).
- Human phrase `派发` at 2026-08-25T12:31:03Z; R2 measure: beam+R0 sweep @ α=1.2 (tmp/intent-hierarchical-vamana-measure-r2.md).
- Human phrase `派发` at 2026-08-25T15:06:47Z; 1T supplementary measure @ locked beam=32/R0=32/α=1.2 (tmp/intent-hierarchical-vamana-measure-1t.md).

