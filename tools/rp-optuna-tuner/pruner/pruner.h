// pruner.h — rp-optuna-tuner: cheap feasibility pruning (copy-then-edit of CAT
// pruner.h, [[BEH-018]] / [[BEH-028]]; namespace cat -> rpt).
//
// Before any full build, drop infeasible / dominated configurations using structural
// properties only:
//   - ef monotonic feasibility (recall non-decreasing in refine_ef)
//   - build-param unimodality (alpha concave penalty around alpha*)
//   - separable resource model (graph CSR + PQ + flat-vec cache + block cache vs cgroup)
//   - cgroup memory budget ([[CON-001]]) + recall target ([[CON-002]])
//
// Offline DSE only ([[ARCH-RPT-001]]); does not enter the search hot path.

#ifndef RPT_TUNER_PRUNER_H
#define RPT_TUNER_PRUNER_H

#include <algorithm>
#include <cstdint>
#include <string>
#include <vector>

#include "../include/rpt_types.h"

namespace rpt {

struct PruneStats {
    int64_t in = 0;             // candidate configs before pruning
    int64_t memory_pruned = 0;  // dropped: predicted RSS > cgroup budget
    int64_t recall_pruned = 0;  // dropped: prior recall < target
    int64_t qps_pruned = 0;     // dropped: prior qps < floor
    int64_t axis_pruned = 0;    // dropped: GBDT axis disabled
    int64_t dominated = 0;      // dropped: Pareto-dominated by another feasible config
    int64_t out = 0;            // feasible configs remaining
};

// Pareto dominance: a dominates b iff a is no worse on every axis and strictly better
// on at least one (higher recall, higher qps, lower predicted RSS all preferred).
inline bool dominates(const TuningKnobs& a, const TuningKnobs& b, const ResourceModel& rm, int cgroup_mb) {
    float ra = prior_recall(a), rb = prior_recall(b);
    float qa = prior_qps(a), qb = prior_qps(b);
    int64_t ma = predict_rss_mb(a, rm, cgroup_mb), mb = predict_rss_mb(b, rm, cgroup_mb);
    bool ge = (ra >= rb) && (qa >= qb) && (ma <= mb);
    bool gt = (ra > rb) || (qa > qb) || (ma < mb);
    return ge && gt;
}

// prune_infeasible: filter `in` → `out` keeping only cheap-feasible, non-dominated
// configs. Returns pruning statistics for reporting.
inline PruneStats prune_infeasible(const std::vector<TuningKnobs>& in,
                                   const ConstraintBudget& budget,
                                   const ResourceModel& rm,
                                   std::vector<TuningKnobs>& out) {
    PruneStats st;
    st.in = (int64_t)in.size();
    out.clear();
    out.reserve(in.size());

    std::vector<TuningKnobs> feasible;
    for (const auto& k : in) {
        if (!budget.enable_gbdt && k.learned_ef) { st.axis_pruned++; continue; }
        int64_t rss = predict_rss_mb(k, rm, budget.cgroup_mb);
        if (rss > budget.cgroup_mb) { st.memory_pruned++; continue; }
        float recall = prior_recall(k);
        if (recall < budget.recall_target) { st.recall_pruned++; continue; }
        if (budget.qps_floor > 0.0f && prior_qps(k) < budget.qps_floor) { st.qps_pruned++; continue; }
        feasible.push_back(k);
    }

    for (size_t i = 0; i < feasible.size(); i++) {
        bool dominated = false;
        for (size_t j = 0; j < feasible.size(); j++) {
            if (i == j) continue;
            if (dominates(feasible[j], feasible[i], rm, budget.cgroup_mb)) { dominated = true; break; }
        }
        if (!dominated) out.push_back(feasible[i]); else st.dominated++;
    }

    st.out = (int64_t)out.size();
    return st;
}

}  // namespace rpt

#endif  // RPT_TUNER_PRUNER_H
