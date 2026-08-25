// vamana_build.cpp — hierarchical-vamana POC builder
//
// Hypothesis (TOPIC.md H0): replace the trunk hnswlib whole-graph build with
//   "HNSW-style layer assignment + per-layer Vamana (GreedySearch + RobustPrune, α)"
//   while keeping the DiskHNSW storage/search shell unchanged (or minimally adapted).
//
// This binary:
//   1. reads fvecs base vectors,
//   2. assigns HNSW geometric levels (level = floor(-ln(U) * mL), mL = 1/ln(M)),
//   3. builds, for each layer l, a Vamana graph over S_l = {i : level[i] >= l},
//   4. exports the result as a GraphStructure (exact format produced by Trunk
//      extract_graph), so the existing bfs_reorder / write_blocks /
//      write_blocks_veconly / gen_route pipeline and DiskHNSW search run unchanged.
//
// Non-goals (documented): no 10B DiskANN shard-merge; no VER/stable-SLA changes;
//   no Trunk src/include/tests edits (BEH-018).
//
// Usage:
//   ./vamana_build <data.fvecs> <out_graph.bin> [--max-points N] [--self-test K]
//     --max-points N : build on first N points only (smoke / subset runs)
//     --self-test K  : after build, run greedy-descent + L0 beam search over the
//                      first K points (leave-one-out) and report Recall@10 vs brute force.
//   Env knobs (INTERFACE.md): HV_M, HV_R0, HV_RUP, HV_BEAM, HV_ALPHA, HV_ALPHA2,
//                             HV_ROUNDS, HV_SEED.

#include "common.h"

#include <algorithm>
#include <chrono>
#include <cfloat>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <queue>
#include <random>
#include <unordered_set>
#include <vector>

#ifdef _OPENMP
#include <omp.h>
#endif

// ---------------------------------------------------------------------------
// Squared L2 distance (matches the search-side l2Distance convention).
// ---------------------------------------------------------------------------
static inline float l2(const float* a, const float* b, int dim) {
    float s = 0.0f;
    for (int i = 0; i < dim; i++) {
        float d = a[i] - b[i];
        s += d * d;
    }
    return s;
}

// ---------------------------------------------------------------------------
// RobustPrune (DiskANN / Vamana). Candidates are node IDs (may include p).
// Returns up to R node IDs.
// ---------------------------------------------------------------------------
static std::vector<uint32_t> robust_prune(
    const std::vector<float>& vec, int dim, uint32_t p,
    std::vector<uint32_t> candidates, float alpha, int R) {

    const float* pvec = &vec[(size_t)p * dim];

    // dedup + drop self
    std::sort(candidates.begin(), candidates.end());
    candidates.erase(std::unique(candidates.begin(), candidates.end()), candidates.end());

    std::vector<std::pair<float, uint32_t>> c;
    c.reserve(candidates.size());
    for (uint32_t v : candidates) {
        if (v == p) continue;
        c.emplace_back(l2(pvec, &vec[(size_t)v * dim], dim), v);
    }
    std::sort(c.begin(), c.end());

    std::vector<uint32_t> kept;
    kept.reserve(R);
    for (auto& [dpv, v] : c) {
        if ((int)kept.size() >= R) break;
        bool ok = true;
        const float* vvec = &vec[(size_t)v * dim];
        for (uint32_t u : kept) {
            float duv = l2(vvec, &vec[(size_t)u * dim], dim);
            if (alpha * duv <= dpv) { ok = false; break; }
        }
        if (ok) kept.push_back(v);
    }
    return kept;
}

// ---------------------------------------------------------------------------
// GreedySearch / beam search over a layer graph.
//   out[p] = neighbor NODE IDs of subset node at position p.
//   vis/cv = caller-owned visited array + generation marker (thread scratch).
// Returns up to L candidate NODE IDs (closest to query at subset position qi).
// ---------------------------------------------------------------------------
static std::vector<uint32_t> greedy_search(
    const std::vector<float>& vec, int dim,
    const std::vector<std::vector<uint32_t>>& out,   // out[pos] = neighbor NODE ids
    const std::vector<int32_t>& pos,                 // node id -> subset position
    const std::vector<uint32_t>& ids,
    size_t qi, int L, uint32_t start_pos,
    std::vector<uint8_t>& vis, uint8_t cv) {

    const float* q = &vec[(size_t)ids[qi] * dim];

    using P = std::pair<float, uint32_t>;  // (dist, subset position)
    std::priority_queue<P, std::vector<P>, std::less<P>> res;      // max by dist (worst on top)
    std::priority_queue<P, std::vector<P>, std::greater<P>> cand;  // min by dist

    uint32_t sid = ids[start_pos];
    float d0 = l2(q, &vec[(size_t)sid * dim], dim);
    cand.emplace(d0, start_pos);
    res.emplace(d0, start_pos);
    vis[sid] = cv;

    while (!cand.empty()) {
        auto [dp, p] = cand.top(); cand.pop();
        if (dp > res.top().first) break;
        for (uint32_t v : out[p]) {          // v = neighbor NODE id
            if (vis[v] == cv) continue;
            vis[v] = cv;
            uint32_t vp = (uint32_t)pos[v];  // subset position
            float d = l2(q, &vec[(size_t)v * dim], dim);
            if ((int)res.size() < L || d < res.top().first) {
                res.emplace(d, vp);
                cand.emplace(d, vp);
                if ((int)res.size() > L) res.pop();
            }
        }
    }

    std::vector<uint32_t> result;
    result.reserve(res.size());
    while (!res.empty()) { result.push_back(ids[res.top().second]); res.pop(); }
    return result;  // node IDs, roughly ascending dist
}

// ---------------------------------------------------------------------------
// Cheap medoid over a random sample (for greedy-search start node).
// ---------------------------------------------------------------------------
static uint32_t sample_medoid(const std::vector<float>& vec, int dim,
                              const std::vector<uint32_t>& ids, uint32_t seed) {
    size_t n = ids.size();
    std::mt19937 rng(seed);
    size_t sample = std::min<size_t>(n, 300);
    std::vector<uint32_t> s;
    s.reserve(sample);
    std::unordered_set<uint32_t> seen;
    while (s.size() < sample) {
        uint32_t v = ids[rng() % n];
        if (seen.insert(v).second) s.push_back(v);
    }
    uint32_t best = s[0];
    float best_sum = FLT_MAX;
    for (uint32_t u : s) {
        const float* uv = &vec[(size_t)u * dim];
        float sum = 0.0f;
        for (uint32_t w : s) sum += l2(uv, &vec[(size_t)w * dim], dim);
        if (sum < best_sum) { best_sum = sum; best = u; }
    }
    return best;
}

// ---------------------------------------------------------------------------
// Build one Vamana layer over node subset `ids`.
// Returns out[position] = neighbor NODE IDs.
// ---------------------------------------------------------------------------
static std::vector<std::vector<uint32_t>> build_vamana_layer(
    const std::vector<float>& vec, int dim, uint32_t N,
    const std::vector<uint32_t>& ids, const std::vector<int32_t>& pos,
    int R, int beam, float alpha, int rounds, uint32_t seed) {

    size_t n = ids.size();
    std::vector<std::vector<uint32_t>> out(n);

    // --- random init: R random neighbors (keeps graph connected) ---
    std::mt19937 rng(seed);
    if (n > 1) {
        for (size_t i = 0; i < n; i++) {
            std::unordered_set<uint32_t> chosen;
            int target = std::min<int>(R, (int)n - 1);
            int guard = 0;
            while ((int)chosen.size() < target && guard++ < target * 20) {
                uint32_t v = ids[rng() % n];
                if (v != ids[i]) chosen.insert(v);
            }
            out[i].assign(chosen.begin(), chosen.end());
        }
    }

    // --- iterative refinement (parallel forward + symmetrize + prune) ---
#ifdef _OPENMP
    int nthreads = omp_get_max_threads();
#else
    int nthreads = 1;
#endif
    std::vector<std::vector<uint8_t>> visited(nthreads, std::vector<uint8_t>(N, 0));
    std::vector<uint8_t> curV(nthreads, 1);

    uint32_t medoid = sample_medoid(vec, dim, ids, seed);
    uint32_t start_pos = (uint32_t)pos[medoid];

    for (int round = 0; round < rounds; round++) {
        // forward pass: READ out (previous graph), WRITE nxt (double-buffered, race-free)
        std::vector<std::vector<uint32_t>> nxt(n);
#pragma omp parallel
        {
#ifdef _OPENMP
            int tid = omp_get_thread_num();
#else
            int tid = 0;
#endif
            auto& vis = visited[tid];
            uint8_t& cv = curV[tid];
#pragma omp for schedule(dynamic, 128)
            for (size_t i = 0; i < n; i++) {
                if (++cv == 0) { std::fill(vis.begin(), vis.end(), 0); cv = 1; }
                auto cand = greedy_search(vec, dim, out, pos, ids, i, beam, start_pos, vis, cv);
                std::vector<uint32_t> merged = cand;
                merged.insert(merged.end(), out[i].begin(), out[i].end());
                nxt[i] = robust_prune(vec, dim, ids[i], std::move(merged), alpha, R);
            }
        }

        // symmetrize (add reverse edges from nxt)
        std::vector<std::vector<uint32_t>> incoming(n);
        for (size_t i = 0; i < n; i++)
            for (uint32_t v : nxt[i]) incoming[pos[v]].push_back(ids[i]);

        // final prune: READ nxt + incoming, WRITE out (race-free)
#pragma omp parallel for schedule(dynamic, 128)
        for (size_t i = 0; i < n; i++) {
            std::vector<uint32_t> merged = nxt[i];
            merged.insert(merged.end(), incoming[i].begin(), incoming[i].end());
            out[i] = robust_prune(vec, dim, ids[i], std::move(merged), alpha, R);
        }
    }

    return out;
}

// ---------------------------------------------------------------------------
// Self-test search: greedy descent (upper levels) + L0 beam search.
// Mirrors DiskHNSW::greedyDescent + searchLayer0 semantics (old-id space).
// ---------------------------------------------------------------------------
struct SearchCtx {
    const std::vector<float>& vec;
    int dim;
    uint32_t N;
    const std::vector<int32_t>& levels;
    const std::vector<std::vector<std::vector<uint32_t>>>& upper;  // [node][level]
    const std::vector<std::vector<uint32_t>>& adj0;
    uint32_t entry;
    int max_level;
};

static uint32_t selftest_descent(const SearchCtx& s, const float* q,
                                 std::vector<uint8_t>& vis, uint8_t& cv) {
    uint32_t curr = s.entry;
    for (int level = s.max_level; level > 0; level--) {
        bool changed = true;
        while (changed) {
            changed = false;
            if (s.levels[curr] < level) break;
            float curDist = l2(q, &s.vec[(size_t)curr * s.dim], s.dim);
            for (uint32_t nb : s.upper[curr][level]) {
                float d = l2(q, &s.vec[(size_t)nb * s.dim], s.dim);
                if (d < curDist) { curDist = d; curr = nb; changed = true; }
            }
        }
    }
    return curr;
}

static std::vector<uint32_t> selftest_l0(const SearchCtx& s, const float* q, uint32_t entry,
                                         int ef, int k, std::vector<uint8_t>& vis, uint8_t& cv) {
    using P = std::pair<float, uint32_t>;
    std::priority_queue<P, std::vector<P>, std::greater<P>> cand;  // min
    std::priority_queue<P, std::vector<P>, std::less<P>> top;      // max (worst)
    float de = l2(q, &s.vec[(size_t)entry * s.dim], s.dim);
    cand.emplace(de, entry);
    top.emplace(de, entry);
    vis[entry] = cv;
    while (!cand.empty()) {
        auto [dp, p] = cand.top(); cand.pop();
        if (dp > top.top().first) break;
        for (uint32_t v : s.adj0[p]) {
            if (vis[v] == cv) continue;
            vis[v] = cv;
            float d = l2(q, &s.vec[(size_t)v * s.dim], s.dim);
            if ((int)top.size() < ef || d < top.top().first) {
                top.emplace(d, v);
                cand.emplace(d, v);
                if ((int)top.size() > ef) top.pop();
            }
        }
    }
    std::vector<std::pair<float, uint32_t>> all;
    while (!top.empty()) { all.push_back(top.top()); top.pop(); }
    std::sort(all.begin(), all.end());
    std::vector<uint32_t> res;
    for (size_t i = 0; i < all.size() && (int)res.size() < k; i++) res.push_back(all[i].second);
    return res;
}

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <data.fvecs> <out_graph.bin>"
                  << " [--max-points N] [--self-test K]" << std::endl;
        return 1;
    }
    std::string data_path = argv[1];
    std::string out_path = argv[2];

    size_t max_points = SIZE_MAX;
    size_t selftest_k = 0;
    for (int i = 3; i < argc; i++) {
        std::string a = argv[i];
        if (a == "--max-points" && i + 1 < argc) max_points = std::stoull(argv[++i]);
        else if (a == "--self-test" && i + 1 < argc) selftest_k = std::stoull(argv[++i]);
        else { std::cerr << "Unknown arg: " << a << std::endl; return 1; }
    }

    // env knobs
    auto env_int = [](const char* k, int dflt) {
        const char* v = std::getenv(k); return v ? std::atoi(v) : dflt;
    };
    auto env_float = [](const char* k, float dflt) {
        const char* v = std::getenv(k); return v ? std::atof(v) : dflt;
    };
    int M_base  = env_int("HV_M", 16);
    int R0      = env_int("HV_R0", 32);
    int Rup     = env_int("HV_RUP", 16);
    int beam    = env_int("HV_BEAM", 64);
    float alpha = env_float("HV_ALPHA", 1.2f);
    float alpha2 = env_float("HV_ALPHA2", 0.0f);
    int rounds  = env_int("HV_ROUNDS", 2);
    uint32_t seed = (uint32_t)env_int("HV_SEED", 42);

    std::cout << "=== hierarchical-vamana builder ===" << std::endl;
    std::cout << "M_base=" << M_base << " R0=" << R0 << " Rup=" << Rup
              << " beam=" << beam << " alpha=" << alpha << " alpha2=" << alpha2
              << " rounds=" << rounds << " seed=" << seed << std::endl;

    // --- read data ---
    int dim;
    size_t num_elements;
    auto t0 = std::chrono::high_resolution_clock::now();
    std::vector<float> data = read_fvecs(data_path, dim, num_elements);
    auto t1 = std::chrono::high_resolution_clock::now();
    std::cout << "Read " << num_elements << " vectors, dim=" << dim
              << " (" << std::chrono::duration<double>(t1 - t0).count() << "s)" << std::endl;

    if (max_points < num_elements) {
        std::cout << "Restricting to first " << max_points << " points (subset run)" << std::endl;
        num_elements = max_points;
        data.resize(num_elements * dim);
    }

    uint32_t N = (uint32_t)num_elements;

    // --- level assignment (HNSW geometric) ---
    double mL = 1.0 / std::log((double)M_base);
    std::mt19937 rng(seed);
    std::uniform_real_distribution<double> U(0.0, 1.0);
    std::vector<int32_t> levels(N, 0);
    int max_level = 0;
    uint32_t entry_point = 0;
    for (uint32_t i = 0; i < N; i++) {
        double u = U(rng);
        int lvl = (int)std::floor(-std::log(u + 1e-12) * mL);
        levels[i] = lvl;
        if (lvl > max_level) { max_level = lvl; entry_point = i; }
    }
    std::cout << "Levels assigned: max_level=" << max_level
              << " entry_point=" << entry_point << std::endl;
    {
        std::vector<int> dist(max_level + 1, 0);
        for (uint32_t i = 0; i < N; i++) dist[levels[i]]++;
        std::cout << "  Level distribution:";
        for (int l = 0; l <= max_level; l++) std::cout << " " << l << ":" << dist[l];
        std::cout << std::endl;
    }

    // --- build per-layer Vamana ---
    // upper[level][node] = out-edges at that level (node IDs)
    std::vector<std::vector<std::vector<uint32_t>>> upper_adj(N);
    for (uint32_t i = 0; i < N; i++)
        if (levels[i] > 0) upper_adj[i].resize(levels[i] + 1);

    std::vector<std::vector<uint32_t>> adj0;  // L0 out-edges, indexed by position
    std::vector<int32_t> pos(N, -1);          // node_id -> subset position (reused per layer)

    auto build_and_store = [&](int layer, int R) -> void {
        std::vector<uint32_t> ids;
        ids.reserve(N / (M_base > 1 ? M_base : 2) + 8);
        for (uint32_t i = 0; i < N; i++)
            if (levels[i] >= layer) ids.push_back(i);
        std::fill(pos.begin(), pos.end(), -1);
        for (size_t p = 0; p < ids.size(); p++) pos[ids[p]] = (int32_t)p;

        std::cout << "Building layer " << layer << " over " << ids.size()
                  << " nodes (R=" << R << ")..." << std::flush;
        auto tl0 = std::chrono::high_resolution_clock::now();
        auto out = build_vamana_layer(data, dim, N, ids, pos, R, beam, alpha, rounds,
                                      seed + (uint32_t)layer * 1000003u);
        auto tl1 = std::chrono::high_resolution_clock::now();
        std::cout << " done (" << std::chrono::duration<double>(tl1 - tl0).count() << "s)"
                  << std::endl;

        size_t edges = 0;
        for (auto& o : out) edges += o.size();
        std::cout << "  layer " << layer << ": " << edges << " edges, avg "
                  << (ids.empty() ? 0.0 : (double)edges / ids.size()) << std::endl;

        if (layer == 0) {
            adj0 = std::move(out);
        } else {
            for (size_t p = 0; p < ids.size(); p++) {
                upper_adj[ids[p]][layer] = std::move(out[p]);
            }
        }
    };

    for (int layer = max_level; layer >= 0; layer--) {
        build_and_store(layer, layer == 0 ? R0 : Rup);
    }

    // optional second pass alpha2 on L0
    if (alpha2 > 0.0f && !adj0.empty()) {
        std::cout << "Second-pass prune on L0 (alpha2=" << alpha2 << ")..." << std::flush;
        std::vector<uint32_t> ids(N);
        for (uint32_t i = 0; i < N; i++) ids[i] = i;
        for (uint32_t i = 0; i < N; i++) pos[i] = (int32_t)i;
#pragma omp parallel for schedule(dynamic, 128)
        for (size_t i = 0; i < N; i++) {
            adj0[i] = robust_prune(data, dim, (uint32_t)i, adj0[i], alpha2, R0);
        }
        std::cout << " done" << std::endl;
    }

    // --- self-test (optional) ---
    if (selftest_k > 0) {
        size_t q = std::min<size_t>(selftest_k, N);
        SearchCtx s{data, dim, N, levels, upper_adj, adj0, entry_point, max_level};
        std::vector<uint8_t> vis(N, 0);
        uint8_t cv = 1;
        int ef = 100, k = 10;
        size_t correct = 0, total = 0;
        auto tq0 = std::chrono::high_resolution_clock::now();
        for (size_t i = 0; i < q; i++) {
            if (++cv == 0) { std::fill(vis.begin(), vis.end(), 0); cv = 1; }
            const float* qv = &data[i * dim];
            uint32_t e = selftest_descent(s, qv, vis, cv);
            auto found = selftest_l0(s, qv, e, ef, k + 1, vis, cv);  // fetch k+1, drop self

            // brute force (leave-one-out)
            std::vector<std::pair<float, uint32_t>> all;
            all.reserve(N);
            for (uint32_t j = 0; j < N; j++) {
                if (j == i) continue;
                all.emplace_back(l2(qv, &data[(size_t)j * dim], dim), j);
            }
            std::sort(all.begin(), all.end());
            std::unordered_set<uint32_t> gt;
            for (int j = 0; j < k; j++) gt.insert(all[j].second);
            int got = 0;
            for (uint32_t v : found) {
                if (v == (uint32_t)i) continue;  // leave-one-out: skip self
                if (gt.count(v)) got++;
                if (got >= k) break;
            }
            correct += got;
            total += k;
        }
        auto tq1 = std::chrono::high_resolution_clock::now();
        std::cout << "=== SELF-TEST Recall@" << k << " = " << (100.0 * correct / total)
                  << "% (" << correct << "/" << total << ") over " << q << " queries ("
                  << std::chrono::duration<double>(tq1 - tq0).count() << "s)" << std::endl;
    }

    // --- export GraphStructure ---
    GraphStructure g;
    g.num_nodes = N;
    g.dim = (uint32_t)dim;
    g.maxM = (uint32_t)Rup;
    g.maxM0 = (uint32_t)R0;
    g.entry_point = entry_point;
    g.max_level = max_level;
    g.data_size = (uint32_t)(dim * sizeof(float));
    g.levels = levels;
    g.vectors = std::move(data);
    g.labels.resize(N);
    for (uint32_t i = 0; i < N; i++) g.labels[i] = i;
    g.adjacency0.resize(N);
    for (uint32_t i = 0; i < N; i++) g.adjacency0[i] = adj0[i];
    g.upper_adjacency = std::move(upper_adj);

    std::cout << "Saving graph structure to " << out_path << "..." << std::endl;
    save_graph_structure(out_path, g);
    std::cout << "Done." << std::endl;
    return 0;
}
