// tune_main.cpp — rp-optuna-tuner POC: offline DSE driver ([[ARCH-RPT-001]])
//
// Copy-then-edit of tools/constraint-aware-tuner/harness/tune_main.cpp ([[BEH-018]]).
// Demonstrates the prune → search → validate loop for the cfg-sla-ef100 / SIFT1M scene
// (512MB cgroup, 16T main gauge) WITHOUT a full build:
//   - CHAT structure-aware pruning (pruner/pruner.h)
//   - "search-first" operating point (ef floor is MEASURED, never the prior — searcher.h)
//   - RP-Tuning α₂ post-prune ladder (graph rewrite, 0 rebuild) vs residual rebuild axes
//   - rebuild-count comparison vs full grid and vs a naive random-search (Optuna-like)
//
// A real round calls run_validate() → scripts/build_pipeline.sh + scripts/run_sustained.sh
// (Trunk pipeline + sustained benchmark). This binary is the *cheap* front end.
//
// Build (topic-internal):
//   g++ -O2 -std=c++17 -Itools/rp-optuna-tuner \
//       -o tools/rp-optuna-tuner/harness-bin/tune_main \
//       tools/rp-optuna-tuner/harness/tune_main.cpp

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "../include/rpt_types.h"
#include "../pruner/pruner.h"
#include "../searcher/searcher.h"

using namespace rpt;

// Representative knob space for the cfg-sla-ef100 scene (the Cartesian "grid" baseline
// the structure-aware search must beat on rebuild count).
static std::vector<TuningKnobs> build_knob_space(bool enable_gbdt) {
    std::vector<TuningKnobs> space;
    int M = 16, Rup = 16, rounds = 3;
    int block_size = 65536, pq_M = 32;
    bool bfs = true, fr = true;
    int threads = 16;

    std::vector<int> R0s{24, 28, 32, 36, 40, 44, 48};
    std::vector<int> beams{24, 32, 48, 64};
    std::vector<float> alphas{0.9f, 1.0f, 1.1f, 1.2f, 1.3f, 1.4f};
    std::vector<int> efs{60, 80, 100, 120, 160, 200};

    for (int R0 : R0s)
        for (int beam : beams)
            for (float alpha : alphas)
                for (int ef : efs) {
                    TuningKnobs k;
                    k.M = M; k.R0 = R0; k.Rup = Rup; k.beam = beam;
                    k.alpha = alpha; k.rounds = rounds;
                    k.block_size = block_size; k.pq_M = pq_M; k.bfs_reorder = bfs;
                    k.refine_ef = ef; k.fine_rerank = fr; k.threads = threads;
                    k.learned_ef = false;
                    space.push_back(k);
                    if (enable_gbdt) { k.learned_ef = true; space.push_back(k); }
                }
    return space;
}

static int self_test(const ResourceModel& rm) {
    int fails = 0;

    // 1) anchor config (R0=40/beam=48/α=1.07/256KB/pq_M=32/ef=100) is cheap-feasible
    TuningKnobs winner;
    winner.R0 = 40; winner.beam = 48; winner.alpha = 1.07f;
    winner.block_size = 262144; winner.pq_M = 32; winner.refine_ef = 100;
    ConstraintBudget b;  // recall_target=0.95, cgroup=512
    if (!cheap_feasible(winner, b, rm)) { std::printf("FAIL: anchor config not feasible\n"); fails++; }
    else std::printf("ok: anchor config cheap-feasible (recall=%.4f rss=%lldMB)\n",
                     prior_recall(winner), (long long)predict_rss_mb(winner, rm, b.cgroup_mb));

    // 1b) the winner at its MEASURED ef=70 floor has prior recall < 0.95 (conservative
    // prior, documented): prior 0.9476 < measured 0.9557. The ef floor is MEASURED, never
    // prior'd (searcher.h CRITICAL).
    {
        TuningKnobs k = winner; k.refine_ef = 70;
        bool conservative = prior_recall(k) < 0.95f;
        std::printf("%s: prior at ef=70 is conservative (%.4f < 0.95; measured floor 0.9557)\n",
                    conservative ? "ok" : "FAIL", prior_recall(k));
        if (!conservative) fails++;
    }

    // 2) ef monotonicity: recall(ef) non-decreasing
    {
        bool mono = true; float prev = -1.0f;
        for (int ef = 40; ef <= 240; ef += 20) {
            TuningKnobs k = winner; k.refine_ef = ef;
            float r = prior_recall(k);
            if (r < prev - 1e-6f) mono = false;
            prev = r;
        }
        std::printf("%s: refine_ef recall monotone non-decreasing\n", mono ? "ok" : "FAIL");
        if (!mono) fails++;
    }

    // 3) alpha2 post-prune lowers prior recall (mild) but costs NO rebuild (structural)
    {
        TuningKnobs kp = winner; kp.alpha2 = 1.4f;
        bool lowered = prior_recall(kp) <= prior_recall(winner);
        std::printf("%s: alpha2=1.4 post-prune does not raise prior recall "
                    "(r(base)=%.4f r(a2)=%.4f)\n",
                    lowered ? "ok" : "FAIL", prior_recall(winner), prior_recall(kp));
        if (!lowered) fails++;
    }

    // 4) resource model: R0 too large exceeds cgroup budget
    {
        TuningKnobs big = winner; big.R0 = 96;
        bool over = predict_rss_mb(big, rm, 512) > 512;
        std::printf("%s: R0=96 exceeds 512MB cgroup (rss=%lldMB)\n",
                    over ? "ok" : "FAIL", (long long)predict_rss_mb(big, rm, 512));
        if (!over) fails++;
    }

    // 5) pruner keeps anchor and drops a memory-infeasible config
    {
        TuningKnobs bad = winner; bad.R0 = 96;
        std::vector<TuningKnobs> in{winner, bad}, out;
        PruneStats st = prune_infeasible(in, b, rm, out);
        bool kept = false;
        for (auto& k : out) if (knobs_key(k) == knobs_key(winner)) kept = true;
        std::printf("%s: pruner keeps anchor & prunes memory-infeasible (out=%lld mem_pruned=%lld)\n",
                    (kept && st.memory_pruned >= 1) ? "ok" : "FAIL",
                    (long long)st.out, (long long)st.memory_pruned);
        if (!(kept && st.memory_pruned >= 1)) fails++;
    }

    // 6) should_probe_gbdt skip gate #1 (pinned: winner 95.57% → skip; high-recall → probe)
    {
        bool winner_skip = !should_probe_gbdt(0.9557f);
        bool highrecall_probe = should_probe_gbdt(0.9796f);
        std::printf("%s: should_probe_gbdt (winner 95.57%% skip / high-recall 97.96%% probe)\n",
                    (winner_skip && highrecall_probe) ? "ok" : "FAIL");
        if (!(winner_skip && highrecall_probe)) fails++;
    }

    // 7) residual rebuild knobs are block/pq_M only (GBDT is NOT a rebuild axis)
    {
        std::vector<TuningKnobs> res = search_residual_knobs(winner, b, rm);
        bool no_gbdt_axis = true;
        for (auto& k : res) if (k.learned_ef) no_gbdt_axis = false;
        std::printf("%s: residual knobs exclude GBDT axis (n=%zu)\n",
                    no_gbdt_axis ? "ok" : "FAIL", res.size());
        if (!no_gbdt_axis) fails++;
    }

    return fails;
}

int main(int argc, char** argv) {
    bool selftest = false;
    for (int i = 1; i < argc; i++) {
        if (!std::strcmp(argv[i], "--self-test")) selftest = true;
        else { std::printf("Unknown arg: %s\n", argv[i]); return 2; }
    }

    ResourceModel rm;
    ConstraintBudget budget;  // recall≥95%, 512MB, 16T, GBDT off
    budget.threads = 16;
    budget.enable_gbdt = false;

    if (selftest) {
        int fails = self_test(rm);
        std::printf("=== self-test %s ===\n", fails == 0 ? "PASS" : "FAIL");
        return fails == 0 ? 0 : 1;
    }

    std::printf("=== rp-optuna-tuner POC DSE driver ===\n");
    std::printf("scene: cfg-sla-ef100 / SIFT1M / cgroup 512MB / 16T (recall>=95%%)\n\n");

    std::vector<TuningKnobs> space = build_knob_space(false);
    int64_t grid_size = (int64_t)space.size();

    // --- prune ---
    std::vector<TuningKnobs> feasible;
    PruneStats st = prune_infeasible(space, budget, rm, feasible);
    std::printf("-- prune (structural, pre-build) --\n");
    std::printf("candidates            : %lld\n", (long long)st.in);
    std::printf("  memory pruned       : %lld\n", (long long)st.memory_pruned);
    std::printf("  recall pruned       : %lld\n", (long long)st.recall_pruned);
    std::printf("  dominated           : %lld\n", (long long)st.dominated);
    std::printf("feasible (non-dominated): %lld\n\n", (long long)st.out);

    // --- search: RP-Tuning α₂ ladder (0 rebuild) vs residual rebuild axes ---
    TuningKnobs anchor;  // winner operating graph (R0=40/beam=48/α=1.07/256KB/pq_M=32)
    anchor.R0 = 40; anchor.beam = 48; anchor.alpha = 1.07f;
    anchor.block_size = 262144; anchor.pq_M = 32; anchor.refine_ef = 70;

    std::vector<float> a2_ladder = search_alpha2_ladder(anchor, 1.0f, 1.6f,
                                                        {1.1f, 1.2f, 1.3f, 1.4f, 1.5f});
    std::vector<TuningKnobs> residual = search_residual_knobs(anchor, budget, rm);

    std::printf("-- search (structure-aware, search-first) --\n");
    std::printf("S0 ef floor calibration      : 0 rebuild (fixed winner artifact)\n");
    std::printf("RP-Tuning alpha2 ladder      : %zu graph rewrites (0 rebuild)\n", a2_ladder.size());
    std::printf("Optuna residual rebuild axes : %zu (each = 1 full Vamana insert)\n", residual.size());
    std::printf("vs full grid                 : %lld\n", (long long)grid_size);
    int64_t optuna_like = grid_size / 3;
    std::printf("vs Optuna-like (~grid/3)     : %lld\n\n", (long long)optuna_like);

    std::printf("NOTE: priors are structural (CHAT-style), NOT measurements. The ef floor is\n");
    std::printf("MEASURED on the artifact (harness/calibrate_s0.py); GBDT is per-artifact retrain\n");
    std::printf("([[BEH-RPT-002]]), never a frozen include/gbdt_model.h on/off. Real numbers come\n");
    std::printf("from scripts/run_sustained.sh + the GBDT probe.\n");
    return 0;
}
