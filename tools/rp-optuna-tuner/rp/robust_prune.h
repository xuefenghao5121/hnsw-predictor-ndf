// robust_prune.h — rp-optuna-tuner: RP-Tuning post-hoc RobustPrune graph rewrite pass
// ([[BEH-RPT-001]] / [[ARCH-RPT-001]]).
//
// Offline graph rewrite on an ALREADY-BUILT dense Vamana graph: for each node u, sort its
// L0 neighbors by distance to u, then keep v iff no already-kept w satisfies
//   alpha2 * dist(v, w) <= dist(u, v).
// This is the standard DiskANN/Vamana RobustPrune α-reachability condition generalised to
// an arbitrary angle α₂ (α₂ == 1 reproduces the MRNG pass in Trunk src/pipeline/
// prune_graph.cpp). It cheapens the α/密度 axis: a ladder of α₂ values rewrites one dense
// base graph instead of requiring one full Vamana insert per α ([[BEH-RPT-001]]).
//
// NOT the search hot path ([[ARCH-RPT-001]]): this pass runs once offline per α₂ and
// rewrites the L0 adjacency; the search stack (Fine Rerank / BlockCache / PQ / prefetch
// semantics) is untouched.
//
// Reads include/common.h (GraphStructure + load/save) as a READ-ONLY Trunk link
// ([[BEH-018]]); MUST NOT write Trunk src/ include/ tests/.

#ifndef RPT_ROBUST_PRUNE_H
#define RPT_ROBUST_PRUNE_H

#include <algorithm>
#include <cstdint>
#include <vector>

#include "common.h"  // Trunk read-only link: GraphStructure, l2 helpers

namespace rpt {

struct RobustPruneStats {
    int64_t nodes = 0;
    int64_t edges_before = 0;
    int64_t edges_after = 0;
    double avg_degree_before = 0.0;
    double avg_degree_after = 0.0;
    double edge_reduction_pct = 0.0;
};

inline float l2_dist_sq(const float* a, const float* b, uint32_t dim) {
    float s = 0.0f;
    for (uint32_t i = 0; i < dim; i++) {
        float d = a[i] - b[i];
        s += d * d;
    }
    return s;
}

// robust_prune_pass: rewrite g.adjacency0 in place (offline). alpha2 is the prune angle;
// alpha2 <= 0 is an identity (no-op) pass. R_min keeps each node connected (pad with
// closest dropped neighbors if the α₂ filter empties the list below R_min); R_max caps
// out-degree. g.vectors must be populated (full load), or the caller must pass base vectors.
inline RobustPruneStats robust_prune_pass(GraphStructure& g, float alpha2,
                                          int R_min = 5, int R_max = 64) {
    RobustPruneStats st;
    st.nodes = (int64_t)g.num_nodes;
    if (alpha2 <= 0.0f) {
        for (uint32_t u = 0; u < g.num_nodes; u++) st.edges_before += (int64_t)g.adjacency0[u].size();
        st.edges_after = st.edges_before;
        return st;  // identity pass
    }
    if (g.vectors.empty() || g.dim == 0) {
        // Caller must provide base vectors; without them the pass cannot rank neighbors.
        throw std::runtime_error("robust_prune_pass: g.vectors empty (load full graph first)");
    }

    for (uint32_t u = 0; u < g.num_nodes; u++) {
        auto& nbrs = g.adjacency0[u];
        st.edges_before += (int64_t)nbrs.size();
        if ((int)nbrs.size() <= R_min) { st.edges_after += (int64_t)nbrs.size(); continue; }

        const float* u_vec = &g.vectors[(size_t)u * g.dim];
        std::vector<std::pair<float, uint32_t>> ordered;
        ordered.reserve(nbrs.size());
        for (uint32_t v : nbrs) {
            ordered.emplace_back(l2_dist_sq(u_vec, &g.vectors[(size_t)v * g.dim], g.dim), v);
        }
        std::sort(ordered.begin(), ordered.end());

        std::vector<uint32_t> kept;
        kept.reserve(std::min<size_t>(nbrs.size(), (size_t)R_max));
        std::vector<const float*> kept_vecs;
        kept_vecs.reserve((size_t)R_max);

        for (auto& [duv, v] : ordered) {
            if ((int)kept.size() >= R_max) break;
            const float* v_vec = &g.vectors[(size_t)v * g.dim];
            bool drop = false;
            for (const float* w_vec : kept_vecs) {
                // RobustPrune α-condition: α₂ · dist(v, w) ≤ dist(u, v)  ⟺  α₂²·d²(v,w) ≤ d²(u,v)
                if (alpha2 * alpha2 * l2_dist_sq(v_vec, w_vec, g.dim) <= duv) {
                    drop = true;
                    break;
                }
            }
            if (!drop) {
                kept.push_back(v);
                kept_vecs.push_back(v_vec);
            }
        }
        // R_min connectivity pad: re-add closest dropped neighbors to keep the list ≥ R_min.
        if ((int)kept.size() < R_min) {
            for (auto& [duv, v] : ordered) {
                if ((int)kept.size() >= R_min) break;
                if (std::find(kept.begin(), kept.end(), v) == kept.end()) kept.push_back(v);
            }
        }
        nbrs = std::move(kept);
        st.edges_after += (int64_t)nbrs.size();
    }

    st.avg_degree_before = st.nodes ? (double)st.edges_before / st.nodes : 0.0;
    st.avg_degree_after = st.nodes ? (double)st.edges_after / st.nodes : 0.0;
    st.edge_reduction_pct = st.edges_before ? (1.0 - (double)st.edges_after / st.edges_before) * 100.0 : 0.0;
    return st;
}

}  // namespace rpt

#endif  // RPT_ROBUST_PRUNE_H
