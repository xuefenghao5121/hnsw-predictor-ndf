// tune_main.cpp — constraint-aware-tuning POC: offline DSE driver ([[ARCH-CAT-001]])
//
// Demonstrates the prune → search → validate loop on the cfg-sla-ef100 / SIFT1M
// scene (512MB cgroup, 16T main gauge) WITHOUT a full build: the pruner + searcher
// operate on cheap structural priors (CHAT-style), and the driver reports:
//   - pruning statistics (hit rate, memory/recall/qps/axis drops, dominated)
//   - the validation path (predicted complete-rebuild count)
//   - the recommended config (to be confirmed by run_validate / real measure)
//   - rebuild-count comparison vs full grid and vs a naive random-search (Optuna-like)
//
// A real round calls run_validate() → scripts/build_pipeline.sh + scripts/run_sustained.sh
// (Trunk pipeline + sustained benchmark). This binary is the *cheap* front end.
//
// Build:
//   g++ -O2 -std=c++17 -Itools/constraint-aware-tuner \
//       -o tools/constraint-aware-tuner/harness-bin/tune_main \
//       tools/constraint-aware-tuner/harness/tune_main.cpp
//
// Run:
//   ./tune_main              # full report on the representative knob space
//   ./tune_main --self-test  # internal invariant checks (exit 0 = pass)

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "../include/cat_types.h"
#include "../pruner/pruner.h"
#include "../searcher/searcher.h"

using namespace cat;

// Representative knob space for the cfg-sla-ef100 scene. The full Cartesian product is
// the "grid" baseline the structure-aware search must beat on rebuild count.
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
                    if (enable_gbdt) {
                        k.learned_ef = true;
                        space.push_back(k);
                    }
                }
    return space;
}

static int self_test(const ResourceModel& rm) {
    int fails = 0;

    // 1) default locked config is cheap-feasible at 512MB / recall≥95%
    TuningKnobs def;  // M16 R0=32 beam=32 alpha=1.2 ef=100 fr=1 t=16
    ConstraintBudget b;  // recall_target=0.95, cgroup=512
    if (!cheap_feasible(def, b, rm)) { printf("FAIL: default config not feasible\n"); fails++; }
    else printf("ok: default locked config cheap-feasible (recall=%.4f rss=%lldMB)\n",
                prior_recall(def), (long long)predict_rss_mb(def, rm, b.cgroup_mb));

    // 2) ef monotonicity: recall(ef) non-decreasing
    {
        bool mono = true;
        float prev = -1.0f;
        for (int ef = 40; ef <= 240; ef += 20) {
            TuningKnobs k = def; k.refine_ef = ef;
            float r = prior_recall(k);
            if (r < prev - 1e-6f) mono = false;
            prev = r;
        }
        printf("%s: refine_ef recall monotone non-decreasing\n", mono ? "ok" : "FAIL");
        if (!mono) fails++;
    }

    // 3) alpha unimodality: recall peaks near alpha*=1.2, lower on both sides
    {
        TuningKnobs kp = def; kp.alpha = 1.2f;
        TuningKnobs klo = def; klo.alpha = 0.8f;
        TuningKnobs khi = def; khi.alpha = 1.6f;
        float rp = prior_recall(kp), rlo = prior_recall(klo), rhi = prior_recall(khi);
        bool unimodal = (rp >= rlo) && (rp >= rhi);
        printf("%s: alpha recall unimodal (peak at 1.2): r(0.8)=%.4f r(1.2)=%.4f r(1.6)=%.4f\n",
               unimodal ? "ok" : "FAIL", rlo, rp, rhi);
        if (!unimodal) fails++;
    }

    // 4) resource model: R0 too large exceeds cgroup budget
    {
        TuningKnobs big = def; big.R0 = 96;
        bool over = predict_rss_mb(big, rm, 512) > 512;
        printf("%s: R0=96 exceeds 512MB cgroup (rss=%lldMB)\n",
               over ? "ok" : "FAIL", (long long)predict_rss_mb(big, rm, 512));
        if (!over) fails++;
    }

    // 5) pruner keeps the known-feasible default and drops a memory-infeasible config
    {
        TuningKnobs bad = def; bad.R0 = 96;
        std::vector<TuningKnobs> in{def, bad}, out;
        PruneStats st = prune_infeasible(in, b, rm, out);
        bool kept = false, dropped = false;
        for (auto& k : out) { if (knobs_key(k) == knobs_key(def)) kept = true; }
        dropped = (st.memory_pruned >= 1);
        printf("%s: pruner keeps default & prunes memory-infeasible (out=%lld mem_pruned=%lld)\n",
               (kept && dropped) ? "ok" : "FAIL", (long long)st.out, (long long)st.memory_pruned);
        if (!(kept && dropped)) fails++;
    }

    // 6) should_probe_gbdt skip gate #1 (DESIGN §2 P4, R6+R8 calibrated; pinned numbers).
    {
        bool winner_skip = !should_probe_gbdt(0.9557f);    // winner 95.57% = +0.57pp → skip
        bool highrecall_probe = should_probe_gbdt(0.9796f); // beam=64 97.96% = +2.96pp → probe
        printf("%s: should_probe_gbdt (winner 95.57%% skip / high-recall 97.96%% probe)\n",
               (winner_skip && highrecall_probe) ? "ok" : "FAIL");
        if (!(winner_skip && highrecall_probe)) fails++;
    }

    return fails;
}

int main(int argc, char** argv) {
    bool selftest = false;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--self-test")) selftest = true;
        else { printf("Unknown arg: %s\n", argv[i]); return 2; }
    }

    ResourceModel rm;              // SIFT1M defaults
    ConstraintBudget budget;       // recall≥95%, 512MB, 16T, GBDT off
    budget.threads = 16;
    budget.enable_gbdt = false;

    if (selftest) {
        int fails = self_test(rm);
        printf("=== self-test %s ===\n", fails == 0 ? "PASS" : "FAIL");
        return fails == 0 ? 0 : 1;
    }

    printf("=== constraint-aware-tuning POC DSE driver ===\n");
    printf("scene: cfg-sla-ef100 / SIFT1M / cgroup 512MB / 16T (recall>=95%%)\n\n");

    bool enable_gbdt = false;
    std::vector<TuningKnobs> space = build_knob_space(enable_gbdt);
    int64_t grid_size = (int64_t)space.size();

    // --- prune ---
    std::vector<TuningKnobs> feasible;
    PruneStats st = prune_infeasible(space, budget, rm, feasible);
    printf("-- prune (structural, pre-build) --\n");
    printf("candidates            : %lld\n", (long long)st.in);
    printf("  memory pruned       : %lld\n", (long long)st.memory_pruned);
    printf("  recall pruned       : %lld\n", (long long)st.recall_pruned);
    printf("  qps pruned          : %lld\n", (long long)st.qps_pruned);
    printf("  axis pruned         : %lld\n", (long long)st.axis_pruned);
    printf("  dominated           : %lld\n", (long long)st.dominated);
    printf("feasible (non-dominated): %lld\n", (long long)st.out);
    double prune_hit = (st.in > 0) ? (double)(st.in - st.out) / st.in : 0.0;
    printf("prune hit rate        : %.1f%%\n\n", prune_hit * 100.0);

    // --- search ---
    std::vector<TuningKnobs> path = search_knobs(feasible, budget, rm);
    printf("-- search (structure-aware) --\n");
    printf("validation path (complete rebuilds) : %zu\n", path.size());
    printf("vs full grid                        : %lld\n", (long long)grid_size);
    // naive random-search / Optuna-like baseline: ~30% of grid
    int64_t optuna_like = grid_size / 3;
    printf("vs Optuna-like (~grid/3)            : %lld\n", (long long)optuna_like);
    printf("rebuild reduction vs grid           : %.1f%%\n",
           grid_size ? (1.0 - (double)path.size() / grid_size) * 100.0 : 0.0);
    printf("rebuild reduction vs Optuna-like    : %.1f%%\n\n",
           optuna_like ? (1.0 - (double)path.size() / optuna_like) * 100.0 : 0.0);

    // --- recommend: best feasible by prior qps with recall>=95% ---
    TuningKnobs best;
    float best_qps = -1.0f;
    for (auto& k : path) {
        if (prior_recall(k) < budget.recall_target) continue;
        float q = prior_qps(k);
        if (q > best_qps) { best_qps = q; best = k; }
    }
    printf("-- recommended config (to confirm by run_validate) --\n");
    printf("knobs     : %s\n", knobs_key(best).c_str());
    printf("prior recall : %.4f\n", prior_recall(best));
    printf("prior QPS    : %.1f\n", prior_qps(best));
    printf("pred RSS     : %lld MB\n", (long long)predict_rss_mb(best, rm, budget.cgroup_mb));
    printf("\nNOTE: priors are structural (CHAT-style), NOT measurements. Real numbers\n");
    printf("require scripts/build_poc.sh + scripts/run_poc_measure.sh (run_validate).\n");

    return 0;
}
