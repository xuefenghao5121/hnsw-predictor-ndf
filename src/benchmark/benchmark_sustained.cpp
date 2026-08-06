// benchmark_sustained.cpp - Multi-round random-sampling sustained query benchmark
//
// Topic: sustained-query-benchmark
// Clauses: BEH-035 (multi-round random sampling), API-019 (CLI),
//          CON-SLA-019 (no warmup of measured queries), CON-SLA-020 (baseline)
// Reference semantics (oracle): MODEL-SUSTAINED-001
//   -> spec/models/sustained-query-measurement.md
// Decision / evidence: DEC-084
//
// Motivation (DEC-083 -> corrected by DEC-084): SLA numbers were produced by a
// harness that ran every measured query once before starting the clock
// ("Search warmup: run all queries once to warm cache"). That measures in-memory
// search, not the disk-resident design target -- QPS was overstated by 1.73-7.60x.
//
// CON-SLA-014 mandated drop_caches BEFORE the run but never constrained what is
// allowed INSIDE the timing window. CON-SLA-019 closes that hole.
//
// This harness samples a fresh random subset from the official SIFT query pool each
// round and performs NO warmup over the measured queries. Only a CPU-frequency spin
// is done. Optional --warmup rounds use DISJOINT seeds (seed_base + 1000000 + w) and
// are excluded from statistics.
//
// Note on curve shape (DEC-084 s4): QPS ramps UP toward a steady state rather than
// decaying. Rotating queries cannot evict query-INDEPENDENT shared state (graph CSR
// ~47MB + PQ codes ~30MB + flat-vec cache ~160MB), which stays resident. Steady-state
// QPS is invariant to per-round N -- that invariance (MODEL-SUSTAINED-001 I1) is what
// proves the measurement tracks a physical quantity rather than a harness artifact.
//
// Usage:
//   ./benchmark_sustained <graph> <bfs> <blocks> <route> <data> <query_pool> <gt> <k> <ef>
//                         [--rounds R] [--per-round N] [--seed S] [--warmup W] [--verbose]
// Env: CACHE_MB=<mb> (required), NUM_THREADS, PQ_CODES_PATH, ... (same as benchmark_diskhnsw)

#include "hnswlib/hnswlib.h"
#include "common.h"
#include "block_cache.h"
#include "layout_provider.h"
#include "replacement_policy.h"
#include "disk_hnsw.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <numeric>
#include <random>
#include <set>
#include <string>
#include <thread>
#include <unordered_set>
#include <vector>

using SearchResult = std::pair<float, uint64_t>;

static size_t getRSS_MB() {
    std::ifstream f("/proc/self/status");
    std::string line;
    while (std::getline(f, line)) {
        if (line.substr(0, 6) == "VmRSS:") {
            size_t val = 0;
            std::sscanf(line.c_str(), "VmRSS: %zu kB", &val);
            return val / 1024;
        }
    }
    return 0;
}

// ---------------------------------------------------------------------------
// GT loading: dual format per API-019
//   .ivecs -> official format: per record { int32 dim; int32 ids[dim] }
//   .bin   -> internal format: { uint32 n; uint32 k; uint64 ids[n*k] }
// ---------------------------------------------------------------------------
static std::vector<std::vector<uint64_t>> read_gt_ivecs(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in.is_open()) throw std::runtime_error("Cannot open GT: " + path);
    in.seekg(0, std::ios::end);
    size_t bytes = in.tellg();
    in.seekg(0);
    int32_t dim = 0;
    in.read(reinterpret_cast<char*>(&dim), sizeof(int32_t));
    if (dim <= 0) throw std::runtime_error("Bad ivecs dim in " + path);
    size_t rec = sizeof(int32_t) + (size_t)dim * sizeof(int32_t);
    if (bytes % rec != 0) throw std::runtime_error("Bad ivecs size in " + path);
    size_t n = bytes / rec;
    in.seekg(0);
    std::vector<std::vector<uint64_t>> gt(n);
    std::vector<int32_t> buf(dim);
    for (size_t i = 0; i < n; i++) {
        int32_t d = 0;
        in.read(reinterpret_cast<char*>(&d), sizeof(int32_t));
        in.read(reinterpret_cast<char*>(buf.data()), (size_t)d * sizeof(int32_t));
        gt[i].resize(d);
        for (int32_t j = 0; j < d; j++) gt[i][j] = (uint64_t)buf[j];
    }
    return gt;
}

static std::vector<std::vector<uint64_t>> read_gt_bin(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in.is_open()) throw std::runtime_error("Cannot open GT: " + path);
    uint32_t n = 0, kk = 0;
    in.read(reinterpret_cast<char*>(&n), sizeof(uint32_t));
    in.read(reinterpret_cast<char*>(&kk), sizeof(uint32_t));
    std::vector<std::vector<uint64_t>> gt(n);
    for (uint32_t i = 0; i < n; i++) {
        gt[i].resize(kk);
        in.read(reinterpret_cast<char*>(gt[i].data()), (size_t)kk * sizeof(uint64_t));
    }
    return gt;
}

static std::vector<std::vector<uint64_t>> read_gt_auto(const std::string& path) {
    if (path.size() >= 6 && path.compare(path.size() - 6, 6, ".ivecs") == 0)
        return read_gt_ivecs(path);
    return read_gt_bin(path);
}

// ---------------------------------------------------------------------------
// Per-round sampling: BEH-035 requires seed-controlled, in-round without
// replacement. Round i uses seed_base + i so a rerun reproduces the sequence.
// ---------------------------------------------------------------------------
static std::vector<size_t> sample_round(size_t pool_size, size_t n, uint64_t seed) {
    std::mt19937_64 rng(seed);
    if (n >= pool_size) {
        std::vector<size_t> all(pool_size);
        std::iota(all.begin(), all.end(), 0);
        std::shuffle(all.begin(), all.end(), rng);
        return all;
    }
    // Partial Fisher-Yates over an index map: O(n) memory-light draw without
    // replacement, no rejection loop.
    std::unordered_map<size_t, size_t> swapped;
    std::vector<size_t> out;
    out.reserve(n);
    for (size_t i = 0; i < n; i++) {
        std::uniform_int_distribution<size_t> dist(i, pool_size - 1);
        size_t j = dist(rng);
        auto itj = swapped.find(j);
        size_t vj = (itj == swapped.end()) ? j : itj->second;
        auto iti = swapped.find(i);
        size_t vi = (iti == swapped.end()) ? i : iti->second;
        out.push_back(vj);
        swapped[j] = vi;
    }
    return out;
}

struct RoundStat {
    size_t round = 0;
    size_t queries = 0;
    double seconds = 0;
    double qps = 0;
    double recall = 0;
    size_t cumulative_unique = 0;
};

int main(int argc, char** argv) {
    if (argc < 10) {
        std::cerr << "Usage: " << argv[0]
                  << " <graph> <bfs> <blocks> <route> <data> <query_pool> <gt> <k> <ef>"
                  << " [--rounds R] [--per-round N] [--seed S] [--warmup W] [--verbose]"
                  << std::endl;
        return 1;
    }

    std::string graph_path  = argv[1];
    std::string bfs_path    = argv[2];
    std::string blocks_path = argv[3];
    std::string route_path  = argv[4];
    std::string data_path   = argv[5];
    std::string pool_path   = argv[6];
    std::string gt_path     = argv[7];
    int k  = atoi(argv[8]);
    int ef = atoi(argv[9]);

    size_t rounds = 10, per_round = 200, warmup_rounds = 0;
    uint64_t seed_base = 42;
    bool verbose = false;
    for (int i = 10; i < argc; i++) {
        std::string a = argv[i];
        auto next = [&]() -> std::string {
            if (i + 1 >= argc) throw std::runtime_error("Missing value for " + a);
            return argv[++i];
        };
        if (a == "--rounds")         rounds = std::stoul(next());
        else if (a == "--per-round") per_round = std::stoul(next());
        else if (a == "--seed")      seed_base = std::stoull(next());
        else if (a == "--warmup")    warmup_rounds = std::stoul(next());
        else if (a == "--verbose")   verbose = true;
        else { std::cerr << "Unknown option: " << a << std::endl; return 1; }
    }

    const char* cache_env = std::getenv("CACHE_MB");
    if (!cache_env) { std::cerr << "ERROR: CACHE_MB required" << std::endl; return 1; }
    size_t cache_mb = std::stoul(cache_env);

    int dim = 0;
    {
        std::ifstream df(data_path, std::ios::binary);
        df.read(reinterpret_cast<char*>(&dim), sizeof(int));
    }

    std::ifstream bf(blocks_path, std::ios::binary);
    BlocksFileHeader bfhdr;
    bf.read(reinterpret_cast<char*>(&bfhdr), sizeof(bfhdr));
    bf.close();
    uint32_t num_blocks = bfhdr.num_blocks;
    uint32_t block_size = bfhdr.block_size;
    size_t mem_slots = cache_mb * 1024 * 1024 / block_size;

    int qdim = 0;
    size_t pool_size = 0;
    std::vector<float> pool = read_fvecs(pool_path, qdim, pool_size);
    auto gt_data = read_gt_auto(gt_path);

    if (gt_data.size() < pool_size) {
        std::cerr << "ERROR: GT has " << gt_data.size() << " entries but pool has "
                  << pool_size << std::endl;
        return 1;
    }
    if (per_round > pool_size) {
        std::cerr << "NOTE: per-round " << per_round << " > pool " << pool_size
                  << ", clamping to pool size" << std::endl;
        per_round = pool_size;
    }

    const char* nt_env = std::getenv("NUM_THREADS");
    int num_threads = nt_env ? atoi(nt_env) : 0;

    std::cout << "=== Sustained Query Benchmark (BEH-035) ===" << std::endl;
    std::cout << "Pool: " << pool_size << " queries (dim=" << qdim << ")"
              << " | GT: " << gt_data.size() << "x" << gt_data[0].size() << std::endl;
    std::cout << "Rounds: " << rounds << " | Per-round: " << per_round
              << " | Seed: " << seed_base;
    if (warmup_rounds) std::cout << " | Warmup rounds: " << warmup_rounds;
    std::cout << std::endl;
    std::cout << "k=" << k << ", ef=" << ef << std::endl;
    std::cout << "Cache: " << cache_mb << "MB (" << mem_slots << " slots, "
              << std::fixed << std::setprecision(1)
              << (100.0 * mem_slots / num_blocks) << "% coverage)" << std::endl;
    std::cout << "Mode: " << (num_threads > 0
                              ? ("CONCURRENT (threads=" + std::to_string(num_threads) + ")")
                              : std::string("BLOCKING")) << std::endl;

    IOConfig odirect_config;
    odirect_config.use_odirect = true;
    odirect_config.drop_page_cache = true;

    auto layout = std::make_unique<BfsLayoutProvider>(route_path, num_blocks);
    auto policy = std::make_unique<LRUPolicy>();
    auto cache  = std::make_unique<BlockCache>(blocks_path, std::move(layout), std::move(policy),
                                               mem_slots, dim, odirect_config);
    auto hnsw = std::make_unique<DiskHNSW>(graph_path, bfs_path, std::move(cache));
    hnsw->setEf(ef);
    hnsw->enableGraphPrefetch(true);

    const char* pq_path_env = std::getenv("PQ_CODES_PATH");
    if (pq_path_env && pq_path_env[0]) hnsw->loadPQCodes(pq_path_env);

    hnsw->resetCacheStats();
    hnsw->resetGraphPrefetchStats();
    std::cout << "RSS after init: " << getRSS_MB() << " MB" << std::endl;

    // CPU frequency ramp only. NO query warmup: warming the measured queries is
    // exactly the DEC-083 defect this harness exists to eliminate.
    {
        volatile double sink = 0;
        for (int i = 0; i < 1000000; i++) sink += i * 1.1;
        if (sink < 0) std::cerr << "(warmup sink)";
    }

    // One round of search over the given pool indices.
    auto run_round = [&](const std::vector<size_t>& idx,
                         std::vector<std::vector<SearchResult>>& results) -> double {
        size_t n = idx.size();
        results.assign(n, {});
        std::vector<float> qbuf(n * (size_t)dim);
        for (size_t i = 0; i < n; i++)
            std::memcpy(&qbuf[i * dim], &pool[idx[i] * (size_t)qdim], (size_t)dim * sizeof(float));

        auto t0 = std::chrono::high_resolution_clock::now();
        if (num_threads > 0) {
            std::atomic<size_t> next_idx{0};
            auto worker = [&]() {
                while (true) {
                    size_t i = next_idx.fetch_add(1);
                    if (i >= n) break;
                    results[i] = hnsw->searchKnn(&qbuf[i * dim], k);
                }
            };
            std::vector<std::thread> threads;
            threads.reserve(num_threads);
            for (int t = 0; t < num_threads; t++) threads.emplace_back(worker);
            for (auto& t : threads) t.join();
        } else {
            for (size_t i = 0; i < n; i++)
                results[i] = hnsw->searchKnn(&qbuf[i * dim], k);
        }
        auto t1 = std::chrono::high_resolution_clock::now();
        return std::chrono::duration<double>(t1 - t0).count();
    };

    auto round_recall = [&](const std::vector<size_t>& idx,
                            const std::vector<std::vector<SearchResult>>& results,
                            size_t& correct_out, size_t& total_out) {
        size_t correct = 0, total = 0;
        for (size_t i = 0; i < idx.size(); i++) {
            const auto& g = gt_data[idx[i]];
            std::set<uint64_t> gt_set;
            for (size_t j = 0; j < g.size() && j < (size_t)k; j++) gt_set.insert(g[j]);
            size_t found = 0;
            for (const auto& [d, id] : results[i]) if (gt_set.count(id)) found++;
            correct += found;
            total   += k;
        }
        correct_out = correct;
        total_out   = total;
    };

    // Warmup rounds use seeds far from the measured range so their samples are
    // an independent draw (they still legitimately populate the cache, which is
    // what a real server would have; they are simply excluded from statistics).
    std::vector<std::vector<SearchResult>> results;
    for (size_t w = 0; w < warmup_rounds; w++) {
        auto idx = sample_round(pool_size, per_round, seed_base + 1000000 + w);
        run_round(idx, results);
    }

    std::unordered_set<size_t> seen;
    std::vector<RoundStat> stats_per_round;
    size_t agg_correct = 0, agg_total = 0, agg_queries = 0;
    double agg_seconds = 0;

    for (size_t r = 1; r <= rounds; r++) {
        auto idx = sample_round(pool_size, per_round, seed_base + r);
        double secs = run_round(idx, results);
        size_t c = 0, t = 0;
        round_recall(idx, results, c, t);
        for (size_t v : idx) seen.insert(v);

        RoundStat rs;
        rs.round             = r;
        rs.queries           = idx.size();
        rs.seconds           = secs;
        rs.qps               = idx.size() / secs;
        rs.recall            = 100.0 * c / t;
        rs.cumulative_unique = seen.size();
        stats_per_round.push_back(rs);

        agg_correct += c;
        agg_total   += t;
        agg_queries += idx.size();
        agg_seconds += secs;

        if (verbose) {
            std::cout << "Round " << std::setw(3) << r
                      << ": QPS=" << std::fixed << std::setprecision(1) << std::setw(9) << rs.qps
                      << "  recall=" << std::setprecision(2) << rs.recall << "%"
                      << "  cum_unique=" << rs.cumulative_unique
                      << std::endl;
        }
    }

    auto& cs = hnsw->getCacheStats();
    double hit_rate = cs.total_accesses > 0
        ? (double)cs.cache_hits.load() / cs.total_accesses.load() * 100 : 0;

    std::cout << "\n=== Aggregate ===" << std::endl;
    std::cout << "Total queries: " << agg_queries << std::endl;
    std::cout << "Total time:    " << std::fixed << std::setprecision(3) << agg_seconds << " s" << std::endl;
    std::cout << "QPS:           " << std::setprecision(1) << (agg_queries / agg_seconds) << std::endl;
    std::cout << "Recall@" << k << ":     " << std::setprecision(2)
              << (100.0 * agg_correct / agg_total) << "%" << std::endl;
    std::cout << "Cumulative unique queries: " << seen.size()
              << " / " << pool_size << std::endl;
    std::cout << "Hit%:          " << std::setprecision(2) << hit_rate << std::endl;
    std::cout << "RSS:           " << getRSS_MB() << " MB" << std::endl;

    // First/last round comparison exposes the cache saturation effect directly.
    if (stats_per_round.size() >= 2) {
        double first = stats_per_round.front().qps;
        double last  = stats_per_round.back().qps;
        std::cout << "\n=== Cache saturation ===" << std::endl;
        std::cout << "Round 1 QPS:   " << std::setprecision(1) << first << std::endl;
        std::cout << "Round " << stats_per_round.size() << " QPS:  " << last << std::endl;
        // Positive = ramp-up (steady state faster than cold start), which is the
        // expected shape: query-independent shared state (graph CSR + PQ codes +
        // flat-vec cache) warms up and cannot be evicted by rotating queries.
        // See MODEL-SUSTAINED-001 / DEC-084 §4.
        std::cout << "Ramp-up:       " << std::setprecision(1)
                  << (100.0 * (last - first) / first) << "%" << std::endl;
    }

    // Machine-readable tail for scripted sweeps (API-019).
    std::cout << "\nCSV_HEADER,round,queries,seconds,qps,recall,cum_unique" << std::endl;
    for (const auto& rs : stats_per_round) {
        std::cout << "CSV_ROW," << rs.round << "," << rs.queries << ","
                  << std::setprecision(6) << rs.seconds << ","
                  << std::setprecision(1) << rs.qps << ","
                  << std::setprecision(2) << rs.recall << ","
                  << rs.cumulative_unique << std::endl;
    }
    // CSV_AGG,rounds,total_queries,total_seconds,qps,recall,unique,last_round_qps
    std::cout << "CSV_AGG," << stats_per_round.size()
              << "," << agg_queries << "," << std::setprecision(6) << agg_seconds
              << "," << std::setprecision(1) << (agg_queries / agg_seconds)
              << "," << std::setprecision(2) << (100.0 * agg_correct / agg_total)
              << "," << seen.size()
              << "," << std::setprecision(1)
              << (stats_per_round.empty() ? 0.0 : stats_per_round.back().qps)
              << std::endl;

    return 0;
}
