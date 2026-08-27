// searcher.h — constraint-aware-tuning: structure-aware search ([[BEH-028]])
//
// After pruning, search the surviving space with structure-aware strategies rather
// than a full grid / black-box (Optuna) sweep.
//
// R3 (DESIGN §Traversal strategy, human 审核): the search is NESTED / COORDINATE
// DESCENT + RE-ENTRY, not a stage1→2→3 one-shot or three isolated-layer scans. The
// couplings are first-class (DESIGN §0): ef↔graph, ef↔layout/block, graph-pack↔block,
// 4KB-page↔block, RSS/cgroup↔block, PQ_M↔rerank↔ef.
//
//   - INNER (0 rebuild): on a FIXED graph+layout, MEASURE the ≥95% REFINE_EF floor
//     (the "operating point"), then compare QPS. ef is never carried across a rebuild.
//   - OUTER (1 rebuild each): (graph, block/layout) combos — block ladder then
//     coordinate descent on R0 → beam → α. Every rebuild re-measures its own ef floor.
//   - RE-ENTRY: after a better graph, re-sweep the block ladder on it (at most once),
//     then optionally one graph re-sweep, if I/O differs enough and budget remains.
//
// CRITICAL (R1 falsification, DESIGN §5): prior_recall / prior-min-ef (40–76) MUST NOT
// be used as the reported operating point. The ef floor is always MEASURED on the actual
// artifact. Priors only PRUNE candidates; they are not SoT.
//
// Returns an ordered vector of build proposals (the rebuild path). refine_ef on each
// entry is a PRIOR hint (for the cheap DSE report) and MUST be overwritten by the
// measured ≥95% ef floor before any QPS comparison. Final selection requires
// run_validate ([[VER-001]]).

#ifndef CAT_TUNER_SEARCHER_H
#define CAT_TUNER_SEARCHER_H

#include <algorithm>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "../include/cat_types.h"

namespace cat {

// MeasuredRecallFn: returns measured Recall@10 for a given refine_ef on the CURRENT
// artifact (real sustained measurement). Monotone non-decreasing in ef.
using MeasuredRecallFn = std::function<float(int ef)>;

// measure_ef_floor: binary search the smallest refine_ef whose MEASURED recall ≥ target
// (with margin), within [lo, hi]. This is the measured operating point — NOT the prior.
// Each probe is a real measurement; the number of probes is O(log range).
inline int measure_ef_floor(const MeasuredRecallFn& measured, float recall_target,
                            int lo, int hi) {
    auto feasible = [&](int ef) { return measured(ef) >= recall_target; };
    if (!feasible(hi)) return hi;   // target unreachable at this build (report hi)
    if (feasible(lo)) return lo;
    while (lo + 1 < hi) {
        int mid = lo + (hi - lo) / 2;
        if (feasible(mid)) hi = mid; else lo = mid;
    }
    return hi;  // smallest measured-feasible ef
}

// GBDT is per-artifact search-side calibration (DESIGN §2 P4, R9 Control pin): it sits at
// the same layer as measure_ef_floor and MUST NOT be pushed onto the rebuild path. The
// probe is gated by should_probe_gbdt(floor_recall) — skip gate #1 (R6+R8 calibrated,
// pinned numbers; do NOT invent new ones). Gates #2 (list headroom) and #3 (sim margin
// sweep) are applied inside scripts/run_gbdt_probe.sh, which needs the PROFILE + trained
// model those gates depend on.
//
// Skip gate #1: leftover `floor_recall − 0.95` ≲ 1pp → skip (winner 95.57% = +0.57pp);
// high-recall beam=64 97.96% = +2.96pp → probe. Leftover is NECESSARY but not sufficient
// (R8 m=0.8 still fails at +2.96pp leftover); the sim gate is the final call.
inline bool should_probe_gbdt(float floor_recall, float recall_target = 0.95f,
                              float leftover_skip_pp = 0.01f) {
    return (floor_recall - recall_target) > leftover_skip_pp;
}

// search_alpha_unimodal: candidate alpha values (each a distinct rebuild). The prior is
// a pruning hint; the measured ef floor is re-derived per artifact after the rebuild.
inline std::vector<float> search_alpha_ladder(const TuningKnobs& base, float amin, float amax,
                                              const std::vector<float>& candidates) {
    std::vector<float> path;
    for (float a : candidates) {
        if (a >= amin && a <= amax) path.push_back(a);
    }
    (void)base;
    return path;
}

// search_r0_ladder: candidate R0 values (each a rebuild), stopped at the memory wall.
inline std::vector<int> search_r0_ladder(const TuningKnobs& base, const ConstraintBudget& b,
                                         const ResourceModel& rm,
                                         const std::vector<int>& candidates) {
    std::vector<int> path;
    for (int r0 : candidates) {
        TuningKnobs k = base; k.R0 = r0;
        if (predict_rss_mb(k, rm, b.cgroup_mb) > b.cgroup_mb) break;  // memory wall
        path.push_back(r0);
    }
    return path;
}

// search_knobs: produce the ordered rebuild path per DESIGN §Traversal strategy (P1–P4).
//
// The ladder is the pinned closed ladder (INTERFACE CAT_BLOCK_*), NOT a Cartesian grid:
//   P1 block ladder  {32K, 128K, 256K}   (64K is the anchor, already built at P0)
//   P2 coordinate    R0 {40,48} → beam {48,64} → α {1.33,1.07}  (anchor R0=32/beam=32/α=1.2)
//   P4 residual      pq_M {16,64} (leftover budget only; GBDT is NOT a rebuild — see should_probe_gbdt)
//
// refine_ef on each entry is a PRIOR hint and MUST be replaced by the measured ≥95%
// ef floor before comparing QPS. The budget (CAT_BUDGET_REBUILDS=16) is enforced by the
// caller; this returns the ordered proposals in the recommended priority order.
inline std::vector<TuningKnobs> search_knobs(const std::vector<TuningKnobs>& feasible,
                                             const ConstraintBudget& budget,
                                             const ResourceModel& rm) {
    TuningKnobs anchor;  // M16 R0=32 beam=32 alpha=1.2 block=64K pq_M=32 (locked default)
    for (const auto& f : feasible) {
        if (knobs_key(f) == knobs_key(anchor)) { anchor = f; break; }
    }

    std::vector<TuningKnobs> path;
    auto push = [&](TuningKnobs k) {
        for (const auto& p : path) if (knobs_key(p) == knobs_key(k)) return;
        path.push_back(k);
    };

    // P1: block ladder on the locked graph (64K anchor excluded — already built at P0).
    for (int blk : {32768, 131072, 262144}) {
        TuningKnobs k = anchor; k.block_size = blk;
        push(k);
    }

    // P2: coordinate descent on the (to-be-chosen) B* — here expressed as the ladder of
    // graph-knob probes relative to the anchor. Each is one rebuild; the measured ef
    // floor is re-derived per artifact after the rebuild.
    for (int r0 : {40, 48}) { TuningKnobs k = anchor; k.R0 = r0; push(k); }
    for (int beam : {48, 64}) { TuningKnobs k = anchor; k.beam = beam; push(k); }
    for (float a : {1.33f, 1.07f}) { TuningKnobs k = anchor; k.alpha = a; push(k); }

    // P4: residual probes (leftover budget only; not the main traverse). The leftover
    // rebuild budget is pq_M ONLY — GBDT is per-artifact search-side calibration
    // (DESIGN §2 P4) and MUST NOT be pushed onto the rebuild path here. GBDT probing is
    // gated separately by should_probe_gbdt(floor_recall) + CAT_GBDT_PROBES (see
    // traverse.py probe_gbdt), and consumes NO rebuild budget (no graph rebuild).
    for (int pq : {16, 64}) { TuningKnobs k = anchor; k.pq_M = pq; push(k); }

    // anchor itself is the P0 reference (0 rebuild); include it for completeness.
    push(anchor);

    // re-filter: keep only cheap-feasible proposals (pruning hint, not measurement).
    std::vector<TuningKnobs> validated;
    for (const auto& k : path) if (cheap_feasible(k, budget, rm)) validated.push_back(k);
    return validated;
}

}  // namespace cat

#endif  // CAT_TUNER_SEARCHER_H
