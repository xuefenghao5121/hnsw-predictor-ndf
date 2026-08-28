// rpt_types.h — rp-optuna-tuner: shared types, resource model, priors
//
// Copy-then-edit from tools/constraint-aware-tuner/include/cat_types.h ([[BEH-018]]).
// Namespace renamed cat -> rpt; TuningKnobs extended with the RP-Tuning post-prune
// ladder `alpha2` ([[BEH-RPT-001]]) and the per-artifact GBDT margin `gbdt_margin`
// ([[BEH-RPT-002]] / [[DEC-004]] amend).
//
// Offline design-space exploration (DSE) harness. Does NOT enter the search hot path
// ([[ARCH-RPT-001]]). The recall/QPS "prior" functions below are *structural* cheap
// proxies used only by the pruner/searcher (CHAT-style) — they are NOT measurements and
// MUST NOT be treated as performance SoT. Real numbers come from run_validate() →
// build + sustained measure ([[VER-001]]/[[VER-003]]).
//
// The priors carry the R3 recalibration from CAT (conservative lower bound on recall;
// ef steepened to the same-build measured slope; no R0/beam boost). They are a PRUNING
// HINT ONLY; the operating point is ALWAYS the MEASURED ≥95% REFINE_EF floor.

#ifndef RPT_TUNER_TYPES_H
#define RPT_TUNER_TYPES_H

#include <cmath>
#include <cstdint>
#include <string>

namespace rpt {

// ---------------------------------------------------------------------------
// TuningKnobs — the full DiskHNSW knob space (INTERFACE.md).
// ---------------------------------------------------------------------------
struct TuningKnobs {
    // build (hierarchical Vamana, [[BEH-027]] / [[ARCH-007]])
    int M = 16;         // HNSW geometric level base
    int R0 = 32;        // L0 max out-degree
    int Rup = 16;       // upper-layer max out-degree
    int beam = 32;      // GreedySearch beam width
    float alpha = 1.2f; // RobustPrune angle
    int rounds = 3;     // refinement rounds

    // RP-Tuning post-prune ladder ([[BEH-RPT-001]]): RobustPrune(alpha2) is a graph
    // REWRITE pass on an already-built dense base graph — NOT a full Vamana insert.
    // alpha2 == 0 disables post-prune (identity pass).
    float alpha2 = 0.0f;

    // pipeline
    int block_size = 65536;  // vecblock size (closed ladder {32K,64K(anchor),128K,256K})
    int pq_M = 32;           // PQ subquantizer count
    bool bfs_reorder = true; // BFS layout reorder

    // search
    int refine_ef = 100;     // search beam (ef-like)
    bool fine_rerank = true; // Fine Rerank ([[BEH-013]])
    int threads = 16;        // sustained measure threads

    // optional GBDT ([[BEH-010]] / [[BEH-RPT-002]]) — per-artifact search-side calibration.
    bool learned_ef = false;
    float gbdt_margin = 1.3f;  // LEARNED_EF margin multiplier (re-swept per artifact)
};

// ConstraintBudget — feasibility constraints ([[CON-001]] / [[CON-002]]).
struct ConstraintBudget {
    float recall_target = 0.95f;  // R* (≥95% recall)
    float qps_floor = 0.0f;       // optional QPS floor (0 = unconstrained)
    int cgroup_mb = 512;          // cgroup memory.max MB
    int rebuild_budget = 0;       // 0 = unlimited
    int threads = 16;             // main gauge; 1 = supplementary gauge
    bool enable_gbdt = false;     // GBDT axis participates only when true
};

// MeasureResult — output of run_validate (real build + sustained measure).
struct MeasureResult {
    float recall = 0.0f;
    float qps = 0.0f;
    float steady_qps = 0.0f;
    int rss_mb = 0;
    double build_seconds = 0.0;
    bool feasible = false;   // satisfies recall_target AND fits cgroup budget
    bool measured = false;   // false when a cheap prior was used instead of a real run
};

// ResourceModel — separable RSS model (CHAT "separable resource model").
// SIFT1M defaults: N=1e6 points, dim=128.
struct ResourceModel {
    int64_t n_points = 1000000;
    int dim = 128;
    double graph_bytes_per_edge = 4.0;  // uint32 adjacency
    double graph_compress_ratio = 0.50; // delta+varint after BFS reorder
    double pq_bytes_per_dim = 1.0;      // 1 byte / dim / point (PQ codes)
    int flat_vec_mb_512 = 160;          // FLAT_VEC_MB for 512MB cgroup
    int flat_vec_mb_256 = 64;           // FLAT_VEC_MB for ≤256MB cgroup
    int cache_mb = 64;                  // CACHE_MB (block cache)
    int fixed_mb = 80;                  // runtime + metadata + code overhead
    double route_bytes_per_block = 16.0;// route/block header metadata per block (DESIGN #5)
};

// cache_slots for a given block_size under a fixed CACHE_MB budget (DESIGN coupling #5).
inline int64_t cache_slots(const TuningKnobs& k, const ResourceModel& rm) {
    int64_t slots = (int64_t)rm.cache_mb * 1024 * 1024 / k.block_size;
    return slots > 0 ? slots : 1;
}

// ---------------------------------------------------------------------------
// Separable resource model: predicted resident RSS (MB).
// ---------------------------------------------------------------------------
inline int64_t predict_rss_mb(const TuningKnobs& k, const ResourceModel& rm, int cgroup_mb) {
    const double MB = 1024.0 * 1024.0;
    double graph_mb = rm.n_points * (double)k.R0 * rm.graph_bytes_per_edge * rm.graph_compress_ratio / MB;
    double pq_mb = rm.n_points * (double)k.pq_M * rm.pq_bytes_per_dim / MB;
    double graph_raw_bytes = rm.n_points * (double)k.R0 * rm.graph_bytes_per_edge;
    double num_blocks = graph_raw_bytes / (double)k.block_size;
    double route_mb = num_blocks * rm.route_bytes_per_block / MB;
    int flat_vec = (cgroup_mb <= 256) ? rm.flat_vec_mb_256 : rm.flat_vec_mb_512;
    double total_mb = graph_mb + pq_mb + route_mb + (double)flat_vec + rm.cache_mb + rm.fixed_mb;
    return (int64_t)std::llround(total_mb);
}

// ---------------------------------------------------------------------------
// Prior: recall as function of knobs (structural, NOT measured). Conservative lower
// bound (R3 recalibration, inherited from CAT). PRUNING HINT ONLY.
// ---------------------------------------------------------------------------
inline float prior_recall(const TuningKnobs& k) {
    double r_ref = 0.9702;                    // anchor: cfg-sla-ef100 default (measured)
    double ef_ref = 100.0;
    double gamma = 0.10;                      // steepened (R1: ef dominates recall)
    double r = r_ref * std::pow((double)k.refine_ef / ef_ref, gamma);

    (void)k.R0; (void)k.beam;                 // near-neutral in measurement; no boost

    // alpha unimodal (RobustPrune angle): peak at alpha* = 1.2, concave penalty both sides
    double alpha_star = 1.2;
    double alpha_width = 0.6;
    double alpha_penalty = std::pow((k.alpha - alpha_star) / alpha_width, 2.0);
    r *= 1.0 - 0.06 * alpha_penalty;

    // RP-Tuning post-prune (alpha2): denser prune → lower recall, mild prior penalty
    if (k.alpha2 > 0.0f) r *= 1.0 - 0.02 * std::max(0.0, (double)k.alpha2 - k.alpha);

    if (k.fine_rerank) r *= 1.0 + 0.015;
    if (k.learned_ef) r *= 1.0 + 0.008;

    if (r > 0.999f) r = 0.999f;
    return (float)r;
}

// ---------------------------------------------------------------------------
// Prior: aggregate QPS as function of knobs (structural, NOT measured).
// ---------------------------------------------------------------------------
inline float prior_qps(const TuningKnobs& k) {
    double base = 5708.4;                      // anchor: cfg-sla-ef100 16T agg QPS
    double q = base;
    q *= std::pow(100.0 / (double)k.refine_ef, 0.75);
    q *= std::pow((double)k.threads / 16.0, 0.88);
    q *= std::pow(32.0 / (double)k.R0, 0.30);
    if (!k.fine_rerank) q *= 1.30;
    if (k.learned_ef) q *= 0.97;               // GBDT predictor adds a small cost
    return (float)q;
}

// ---------------------------------------------------------------------------
// Feasibility judgement (cheap, pre-build): [[CON-001]] cgroup memory + recall.
// ---------------------------------------------------------------------------
inline bool cheap_feasible(const TuningKnobs& k, const ConstraintBudget& b, const ResourceModel& rm) {
    if (predict_rss_mb(k, rm, b.cgroup_mb) > b.cgroup_mb) return false;   // memory budget
    if (prior_recall(k) < b.recall_target) return false;                 // recall lower bound
    if (b.qps_floor > 0.0f && prior_qps(k) < b.qps_floor) return false;  // qps floor
    if (b.enable_gbdt == false && k.learned_ef) return false;            // axis disabled
    return true;
}

// Human-readable knob key (for logs / evidence).
inline std::string knobs_key(const TuningKnobs& k) {
    char buf[192];
    std::snprintf(buf, sizeof(buf),
                  "M%d_R0%d_Rup%d_beam%d_a%.2f_a2%.2f_r%d_blk%d_pqM%d_ef%d_fr%d_t%d_gbdt%d_m%.2f",
                  k.M, k.R0, k.Rup, k.beam, k.alpha, k.alpha2, k.rounds,
                  k.block_size, k.pq_M, k.refine_ef, k.fine_rerank ? 1 : 0,
                  k.threads, k.learned_ef ? 1 : 0, k.gbdt_margin);
    return std::string(buf);
}

}  // namespace rpt

#endif  // RPT_TUNER_TYPES_H
