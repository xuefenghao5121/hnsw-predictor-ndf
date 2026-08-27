// cat_types.h — constraint-aware-tuning: shared types, resource model, priors
//
// Offline design-space exploration (DSE) harness. Does NOT enter the search hot path
// ([[ARCH-009]]). The recall/QPS "prior" functions below are *structural* cheap
// proxies used only by the pruner/searcher (CHAT-style: ef monotonicity, build-param
// unimodality, separable resource model) — they are NOT measurements and MUST NOT be
// treated as performance SoT. Real numbers come from run_validate() → build + sustained
// measure ([[VER-001]]/[[VER-003]]).
//
// R3 recalibration (post R1 falsification, DESIGN §5):
//   - prior_recall is now a CONSERVATIVE LOWER BOUND (under-estimates recall). It drops
//     the optimistic R0/beam boosts that made R1 predict "ef=40–76 is ≥95%" when measured
//     recall was 69–93%. The ef exponent was steepened to the same-build measured slope
//     (ef=46→0.917 vs ef=100→0.970) with safety margin.
//   - Prior ef is a PRUNING hint only. The reported operating point is ALWAYS the
//     MEASURED ≥95% REFINE_EF floor on the actual artifact (see searcher / traverse
//     driver), never prior_recall / prior-min-ef.
//   - predict_rss_mb now accounts for block_size (DESIGN coupling #5): route/block
//     metadata ∝ num_blocks = f(block_size); cache_slots = CACHE_MB / block_size.
//
// Copy-then-edit note ([[BEH-018]]): promoted from poc/ to tools/constraint-aware-tuner/.
// Offline DSE only; Trunk src/ + include/ search path is untouched.

#ifndef CAT_TUNER_TYPES_H
#define CAT_TUNER_TYPES_H

#include <cmath>
#include <cstdint>
#include <string>

namespace cat {

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

    // pipeline
    int block_size = 65536;  // vecblock size (CAT_BLOCK_SIZE: {32K,64K(anchor),128K,256K})
    int pq_M = 32;           // PQ subquantizer count
    bool bfs_reorder = true; // BFS layout reorder

    // search
    int refine_ef = 100;     // search beam (ef-like)
    bool fine_rerank = true; // Fine Rerank ([[BEH-013]])
    int threads = 16;        // sustained measure threads

    // optional GBDT ([[BEH-010]]) — axis only, not promoted ([[CON-001]] / [[CON-002]])
    bool learned_ef = false;
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

// cache_slots for a given block_size under a fixed CACHE_MB budget (DESIGN coupling #5):
// slots ≈ CACHE_MB / block_size. Larger blocks → fewer slots → lower block-cache coverage.
inline int64_t cache_slots(const TuningKnobs& k, const ResourceModel& rm) {
    int64_t slots = (int64_t)rm.cache_mb * 1024 * 1024 / k.block_size;
    return slots > 0 ? slots : 1;
}

// ---------------------------------------------------------------------------
// Separable resource model: predicted resident RSS (MB).
// graph CSR ≈ R0*N*edge_bytes*compress ; PQ ≈ N*pq_M ; flat-vec cache ; block cache ;
// route/block metadata ∝ num_blocks = f(block_size) (DESIGN coupling #5).
// ---------------------------------------------------------------------------
inline int64_t predict_rss_mb(const TuningKnobs& k, const ResourceModel& rm, int cgroup_mb) {
    const double MB = 1024.0 * 1024.0;
    double graph_mb = rm.n_points * (double)k.R0 * rm.graph_bytes_per_edge * rm.graph_compress_ratio / MB;
    double pq_mb = rm.n_points * (double)k.pq_M * rm.pq_bytes_per_dim / MB;
    // route/block metadata: ~1 route entry per block; num_blocks ≈ graph bytes / block_size
    double graph_raw_bytes = rm.n_points * (double)k.R0 * rm.graph_bytes_per_edge;
    double num_blocks = graph_raw_bytes / (double)k.block_size;
    double route_mb = num_blocks * rm.route_bytes_per_block / MB;
    int flat_vec = (cgroup_mb <= 256) ? rm.flat_vec_mb_256 : rm.flat_vec_mb_512;
    double total_mb = graph_mb + pq_mb + route_mb + (double)flat_vec + rm.cache_mb + rm.fixed_mb;
    return (int64_t)std::llround(total_mb);
}

// ---------------------------------------------------------------------------
// Prior: recall as function of knobs (structural, NOT measured).
//
// R3 recalibration: CONSERVATIVE LOWER BOUND. R1 falsified the optimistic γ=0.045 +
// R0^0.08/beam^0.02 boost path: prior claimed ef=40–76 was ≥95%-feasible when measured
// recall was 69–93%. Root cause: (a) the ef-recall anchor leaves little headroom below
// ef=100 (same-build measured ef=46→0.917 vs ef=100→0.970), and (b) R0/beam boosts were
// far too large (measured R0 36→48 at ef=40 moved recall only +1.45pp, not +3.3%).
//
// So the prior now:
//   - anchors at ef=100 → 0.9702 (measured), drops recall steeply with ef (exponent
//     ≈ measured 0.073 slope, padded to 0.10 for safety margin),
//   - applies NO R0/beam recall boost (they are near-neutral in measurement),
//   - keeps alpha unimodal penalty + fine_rerank lift + small learned_ef lift.
//
// It is a PRUNING HINT ONLY. The operating point is the MEASURED ef floor.
// ---------------------------------------------------------------------------
inline float prior_recall(const TuningKnobs& k) {
    double r_ref = 0.9702;                    // anchor: cfg-sla-ef100 default (measured)
    double ef_ref = 100.0;
    double gamma = 0.10;                      // steepened (R1: ef dominates recall)
    double r = r_ref * std::pow((double)k.refine_ef / ef_ref, gamma);

    // R0 / beam: near-neutral in measurement (R1 #10–#13); NO boost so prior stays a
    // conservative lower bound.
    (void)k.R0; (void)k.beam;

    // alpha unimodal (RobustPrune angle): peak at alpha* = 1.2, concave penalty both sides
    double alpha_star = 1.2;
    double alpha_width = 0.6;
    double alpha_penalty = std::pow((k.alpha - alpha_star) / alpha_width, 2.0);
    r *= 1.0 - 0.06 * alpha_penalty;          // mild symmetric penalty

    // fine_rerank boosts recall
    if (k.fine_rerank) r *= 1.0 + 0.015;

    // optional GBDT axis ([[CON-CAT-001]]): modest recall lift when enabled
    if (k.learned_ef) r *= 1.0 + 0.008;

    if (r > 0.999f) r = 0.999f;
    return (float)r;
}

// ---------------------------------------------------------------------------
// Prior: aggregate QPS as function of knobs (structural, NOT measured).
// QPS is monotonically non-increasing in ef (more beam → more distance compute),
// sublinear in threads, decreasing in R0 (more edges → more I/O), higher without
// fine_rerank (cheaper search but lower recall).
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
// NOTE: recall check uses the CONSERVATIVE prior. A config that fails the prior recall
// check is dropped; a config that passes still MUST be measured to confirm ≥95% recall.
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
    char buf[160];
    std::snprintf(buf, sizeof(buf),
                  "M%d_R0%d_Rup%d_beam%d_a%.2f_r%d_blk%d_pqM%d_ef%d_fr%d_t%d_gbdt%d",
                  k.M, k.R0, k.Rup, k.beam, k.alpha, k.rounds,
                  k.block_size, k.pq_M, k.refine_ef, k.fine_rerank ? 1 : 0,
                  k.threads, k.learned_ef ? 1 : 0);
    return std::string(buf);
}

}  // namespace cat

#endif  // CAT_TUNER_TYPES_H
