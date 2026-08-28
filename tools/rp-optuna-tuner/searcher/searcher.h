// searcher.h — rp-optuna-tuner: structure-aware search (copy-then-edit of CAT
// searcher.h, [[BEH-018]] / [[BEH-028]]; namespace cat -> rpt).
//
// After pruning, search the surviving space with structure-aware strategies. For R0 the
// search surface is the DESIGN §2 "search-first" shape: on a FIXED artifact, MEASURE the
// ≥95% REFINE_EF floor (the "operating point") BEFORE spending any rebuild budget. The
// rebuild axes are then split into (a) RP-Tuning post-prune (graph rewrite, no rebuild)
// and (b) Optuna TPE over the residual axes (each trial = one full rebuild, budgeted by
// RPT_BUDGET_REBUILDS).
//
// CRITICAL (R1 falsification, DESIGN §5): prior_recall / prior-min-ef MUST NOT be used
// as the reported operating point. The ef floor is always MEASURED on the actual
// artifact. Priors only PRUNE candidates; they are not SoT.

#ifndef RPT_TUNER_SEARCHER_H
#define RPT_TUNER_SEARCHER_H

#include <algorithm>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "../include/rpt_types.h"

namespace rpt {

// MeasuredRecallFn: returns measured Recall@10 for a given refine_ef on the CURRENT
// artifact (real sustained measurement). Monotone non-decreasing in ef.
using MeasuredRecallFn = std::function<float(int ef)>;

// measure_ef_floor: binary search the smallest refine_ef whose MEASURED recall ≥ target
// (with margin), within [lo, hi]. This is the measured operating point — NOT the prior.
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

// GBDT is per-artifact search-side calibration ([[BEH-RPT-002]]): it sits at the same
// layer as measure_ef_floor and MUST NOT be pushed onto the rebuild path. Skip gate #1
// (R6+R8 calibrated, pinned numbers): leftover `floor_recall − 0.95` ≲ 1pp → skip.
inline bool should_probe_gbdt(float floor_recall, float recall_target = 0.95f,
                              float leftover_skip_pp = 0.01f) {
    return (floor_recall - recall_target) > leftover_skip_pp;
}

// RP-Tuning post-prune ladder: candidate alpha2 values (graph rewrite, NOT a rebuild).
// Each alpha2 is a RobustPrune(alpha2) pass on the same dense base graph.
inline std::vector<float> search_alpha2_ladder(const TuningKnobs& base, float a2min, float a2max,
                                               const std::vector<float>& candidates) {
    std::vector<float> path;
    for (float a : candidates) {
        if (a >= a2min && a <= a2max) path.push_back(a);
    }
    (void)base;
    return path;
}

// Residual rebuild axes handed to Optuna (block ladder / pq_M / beam·R0 if RP can't
// cover them). Each returned knob is a distinct FULL rebuild; refine_ef is a PRIOR hint
// and MUST be replaced by the measured ≥95% ef floor before any QPS comparison.
inline std::vector<TuningKnobs> search_residual_knobs(const TuningKnobs& anchor,
                                                      const ConstraintBudget& budget,
                                                      const ResourceModel& rm) {
    std::vector<TuningKnobs> path;
    auto push = [&](TuningKnobs k) {
        for (const auto& p : path) if (knobs_key(p) == knobs_key(k)) return;
        path.push_back(k);
    };

    // block ladder (RP does NOT cheapen block/PQ_M/BFS reorder — [[BEH-RPT-001]])
    for (int blk : {32768, 131072, 262144}) {
        TuningKnobs k = anchor; k.block_size = blk; push(k);
    }
    // pq_M residual
    for (int pq : {16, 64}) { TuningKnobs k = anchor; k.pq_M = pq; push(k); }

    // re-filter: keep only cheap-feasible proposals (pruning hint, not measurement).
    std::vector<TuningKnobs> validated;
    for (const auto& k : path) if (cheap_feasible(k, budget, rm)) validated.push_back(k);
    return validated;
}

}  // namespace rpt

#endif  // RPT_TUNER_SEARCHER_H
