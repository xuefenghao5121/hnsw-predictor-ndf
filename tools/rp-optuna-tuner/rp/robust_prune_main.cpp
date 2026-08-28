// robust_prune_main.cpp — rp-optuna-tuner: offline RobustPrune(α₂) CLI ([[ARCH-RPT-001]]).
//
// Runs the RP-Tuning post-hoc RobustPrune graph rewrite pass (rp/robust_prune.h) on an
// already-built Vamana graph, producing a pruned graph.bin with identical on-disk format.
// This is the concrete "graph rewrite pass" behind BEH-RPT-001: a ladder of α₂ values
// rewrites one dense base graph instead of N full Vamana inserts.
//
// Usage:
//   ./robust_prune_main <graph.bin> <base.fvecs> <out_graph.bin> <alpha2> [R_min=5] [R_max=64]
//
// Build (topic-internal; reads include/common.h as READ-ONLY Trunk link):
//   g++ -O3 -std=c++17 -I../../include -I../../../include \
//       -o ../harness-bin/robust_prune_main rp/robust_prune_main.cpp
//
// NOT the search hot path. Does NOT write Trunk src/ include/ tests/.

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "common.h"
#include "../rp/robust_prune.h"

int main(int argc, char** argv) {
    if (argc < 5) {
        std::fprintf(stderr,
            "Usage: %s <graph.bin> <base.fvecs> <out_graph.bin> <alpha2> [R_min=5] [R_max=64]\n",
            argv[0]);
        return 1;
    }
    std::string graph_path = argv[1];
    std::string vec_path = argv[2];
    std::string out_path = argv[3];
    float alpha2 = (float)std::atof(argv[4]);
    int R_min = argc > 5 ? std::atoi(argv[5]) : 5;
    int R_max = argc > 6 ? std::atoi(argv[6]) : 64;

    std::printf("=== RP-Tuning RobustPrune (offline graph rewrite) ===\n");
    std::printf("graph=%s  base=%s  out=%s  alpha2=%.3f  R_min=%d  R_max=%d\n",
                graph_path.c_str(), vec_path.c_str(), out_path.c_str(), alpha2, R_min, R_max);

    GraphStructure g = load_graph_structure(graph_path);
    if (g.vectors.empty()) {
        std::printf("graph has no vectors; loading base from %s ...\n", vec_path.c_str());
        int dim; size_t count;
        g.vectors = read_fvecs(vec_path, dim, count);
        g.dim = (uint32_t)dim;
        if (count != g.num_nodes) {
            std::fprintf(stderr, "ERROR: vector count mismatch (%zu vs %u)\n", count, g.num_nodes);
            return 1;
        }
    }

    rpt::RobustPruneStats st = rpt::robust_prune_pass(g, alpha2, R_min, R_max);
    std::printf("nodes            : %lld\n", (long long)st.nodes);
    std::printf("edges before     : %lld (avg %.2f)\n", (long long)st.edges_before, st.avg_degree_before);
    std::printf("edges after      : %lld (avg %.2f)\n", (long long)st.edges_after, st.avg_degree_after);
    std::printf("edge reduction   : %.2f%%\n", st.edge_reduction_pct);

    save_graph_structure(out_path, g);
    std::printf("Done.\n");
    return 0;
}
