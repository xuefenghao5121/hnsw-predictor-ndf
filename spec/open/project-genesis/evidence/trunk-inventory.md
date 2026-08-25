# Trunk Inventory — observed (genesis_design)

> bootstrap: adopt | hop: genesis_design
> observed_trunk_sha: d0ae5dd4bdd44af73498f98ea1ac0b86cee0f755

## include/ (public headers, 14)

- block_cache.h
- block_heat_evaluator.h
- common.h
- disk_hnsw.h
- gbdt_model.h
- graph_prefetcher.h
- io_uring_wrapper.h
- layout_provider.h
- replacement_policy.h
- simd.h
- simd_arm.h
- simd_scalar.h
- simd_x86.h

## src/ (implementation)

- core/disk_hnsw.cpp
- core/block_cache.cpp
- core/graph_prefetcher.cpp
- pipeline/build_index.cpp, extract_graph.cpp, bfs_reorder.cpp, write_blocks.cpp,
  write_blocks_veconly.cpp, write_pq_blocks.cpp, gen_route.cpp, verify.cpp,
  prune_graph.cpp, shuffle_vecblocks.cpp, cluster_reorder.cpp
- benchmark/benchmark_sustained.cpp, benchmark_diskhnsw.cpp, benchmark_hnswlib_native.cpp
- test/test_block_cache.cpp, test_disk_hnsw.cpp, test_pq_search_quality.cpp

## Product NDF written (draft)

- spec/00-charter/charter.md — CHR-001..004, DEF-001
- spec/10-architecture/architecture.md — ARCH-001..006
- spec/20-behavior/behavior.md — BEH-001..016
- spec/30-interfaces/interfaces.md — API-001..012
- spec/40-constraints/constraints.md — CON-001..006, CON-SLA-001..006
- spec/50-verification/verification.md — VER-001..008
- spec/decisions/dec-adopt-and-measurement.md — DEC-001..002
- spec/INDEX.md, spec/graph.json (regenerated via ndf_index.py index)

## Post checks

- `python3 spec/meta/tools/ndf_index.py validate` → clauses:114, dangling_refs:1
  (pre-existing meta placeholder PREFIX-AREA-NNN→OTHER-ID), unlinked:11 (warnings)
- `python3 spec/meta/tools/ndf_graphcheck.py` → 0 error(s), 11 warning(s)
