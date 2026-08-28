// benchmark_llsp.cpp — CAT R5 GBDT retrain profiling runner
// copy-then-edit from sibling poc/gbdt-learned-pruning/benchmark_llsp.cpp ([[BEH-018]] recipe):
//   - GT loading switched to this repo's dual-format reader (.ivecs official / .bin internal, API-019)
//   - repo-relative include paths for this poc layout
// Runs the official 10K query pool once warm + once timed (same as recipe); with
// PROFILE_LLSP=1 the DiskHNSW core (harness/disk_hnsw_llsp.cpp) dumps [LLSP] lines to
// stderr for BOTH passes -> consumers take the LAST 10000 lines (timed pass, qid order
// == pool order under NUM_THREADS=1).
// Usage: ./benchmark_llsp <graph> <bfs> <blocks> <route> <data> <query> <gt> <k> <ef> <num_queries>
// Env: CACHE_MB (required), PQ_CODES_PATH, REFINE_EF, NUM_THREADS, PROFILE_LLSP, ...
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
#include <set>
#include <string>
#include <thread>
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

// GT loading: dual format per API-019 (copied from src/benchmark/benchmark_sustained.cpp)
//   .ivecs -> official format: per record { int32 dim; int32 ids[dim] }
//   .bin   -> internal format: { uint32 n; uint32 k; uint64 ids[n*k] }
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

int main(int argc, char** argv) {
    if (argc < 11) {
        std::cerr << "Usage: " << argv[0]
                  << " <graph> <bfs> <blocks> <route> <data> <query> <gt> <k> <ef> <num_queries>"
                  << std::endl;
        return 1;
    }

    std::string graph_path = argv[1];
    std::string bfs_path = argv[2];
    std::string blocks_path = argv[3];
    std::string route_path = argv[4];
    std::string data_path = argv[5];  // only used to get dim
    std::string query_path = argv[6];
    std::string gt_path = argv[7];
    int k = atoi(argv[8]);
    int ef = atoi(argv[9]);
    int num_query = atoi(argv[10]);

    const char* cache_env = std::getenv("CACHE_MB");
    if (!cache_env) { std::cerr << "ERROR: CACHE_MB required" << std::endl; return 1; }
    size_t cache_mb = std::stoul(cache_env);

    // Only read dim from data file header (don't load full data!)
    int dim;
    {
        std::ifstream df(data_path, std::ios::binary);
        df.read(reinterpret_cast<char*>(&dim), sizeof(int));
    }

    // Read block file header
    std::ifstream bf(blocks_path, std::ios::binary);
    BlocksFileHeader bfhdr;
    bf.read(reinterpret_cast<char*>(&bfhdr), sizeof(bfhdr));
    bf.close();
    uint32_t num_blocks = bfhdr.num_blocks;
    uint32_t block_size = bfhdr.block_size;
    size_t mem_slots = cache_mb * 1024 * 1024 / block_size;

    // Read queries (small)
    int qdim;
    size_t num_queries_file;
    std::vector<float> query_data = read_fvecs(query_path, qdim, num_queries_file);
    if ((size_t)num_query > num_queries_file) num_query = num_queries_file;

    auto gt_data = read_gt_auto(gt_path);

    std::cout << "=== DiskHNSW LLSP Profiling ===" << std::endl;
    std::cout << "k=" << k << ", ef=" << ef << ", queries=" << num_query << std::endl;
    std::cout << "Blocks: " << num_blocks << ", block_size=" << block_size << std::endl;
    std::cout << "Cache: " << cache_mb << "MB (" << mem_slots << " slots, "
              << std::fixed << std::setprecision(1) << (100.0 * mem_slots / num_blocks)
              << "% coverage)" << std::endl;

    IOConfig odirect_config;
    odirect_config.use_odirect = true;
    odirect_config.drop_page_cache = true;

    auto layout = std::make_unique<BfsLayoutProvider>(route_path, num_blocks);
    auto policy = std::make_unique<LRUPolicy>();
    auto cache = std::make_unique<BlockCache>(blocks_path, std::move(layout), std::move(policy),
                                               mem_slots, dim, odirect_config);
    auto hnsw = std::make_unique<DiskHNSW>(graph_path, bfs_path, std::move(cache));
    hnsw->setEf(ef);
    hnsw->enableGraphPrefetch(true);

    const char* pq_path_env = std::getenv("PQ_CODES_PATH");
    if (pq_path_env && pq_path_env[0]) {
        hnsw->loadPQCodes(pq_path_env);
    }

    hnsw->resetCacheStats();
    hnsw->resetGraphPrefetchStats();

    std::cout << "RSS after init: " << getRSS_MB() << " MB" << std::endl;

    // CPU warmup: spin to ramp up frequency
    volatile double warm_sink = 0;
    for (int i = 0; i < 1000000; i++) warm_sink += i * 1.1;
    if (warm_sink < 0) std::cerr << "(warmup sink)";

    // Search warmup: run all queries once to warm cache + CPU
    const char* bs_env = std::getenv("BATCH_SIZE");
    int batch_size = bs_env ? atoi(bs_env) : 0;
    const char* nt_env = std::getenv("NUM_THREADS");
    int num_threads = nt_env ? atoi(nt_env) : 0;

    if (num_threads > 0) {
        std::cout << "Mode: CONCURRENT (threads=" << num_threads << ")" << std::endl;
        std::atomic<size_t> warm_idx{0};
        auto warm_worker = [&]() {
            while (true) {
                size_t i = warm_idx.fetch_add(1);
                if ((int)i >= num_query) break;
                hnsw->searchKnn(&query_data[i * dim], k);
            }
        };
        std::vector<std::thread> warm_threads;
        warm_threads.reserve(num_threads);
        for (int t = 0; t < num_threads; t++)
            warm_threads.emplace_back(warm_worker);
        for (auto& t : warm_threads) t.join();
    } else if (batch_size > 0) {
        std::cout << "Mode: NON-BLOCKING (batch_size=" << batch_size << ")" << std::endl;
        std::vector<float> warmup_q(std::min(num_query, 10) * dim);
        std::memcpy(warmup_q.data(), query_data.data(), warmup_q.size() * sizeof(float));
        hnsw->batchSearch(warmup_q, k, batch_size);
    } else {
        std::cout << "Mode: BLOCKING (single query)" << std::endl;
        for (int i = 0; i < num_query; i++)
            hnsw->searchKnn(&query_data[i * dim], k);
    }

    // Timed search (sequential when NUM_THREADS=1 -> qid order == pool order)
    std::vector<double> latencies(num_query);
    std::vector<std::vector<SearchResult>> results(num_query);

    auto t0 = std::chrono::high_resolution_clock::now();
    if (num_threads > 0) {
        std::vector<float> all_q(num_query * dim);
        std::memcpy(all_q.data(), query_data.data(), all_q.size() * sizeof(float));
        std::atomic<size_t> next_idx{0};
        std::vector<double> mt_latencies(num_query);
        auto worker = [&]() {
            while (true) {
                size_t i = next_idx.fetch_add(1);
                if ((int)i >= num_query) break;
                auto q0 = std::chrono::high_resolution_clock::now();
                results[i] = hnsw->searchKnn(&all_q[i * dim], k);
                auto q1 = std::chrono::high_resolution_clock::now();
                mt_latencies[i] = std::chrono::duration<double, std::micro>(q1 - q0).count();
            }
        };
        std::vector<std::thread> threads;
        threads.reserve(num_threads);
        for (int t = 0; t < num_threads; t++)
            threads.emplace_back(worker);
        for (auto& t : threads) t.join();
        latencies = std::move(mt_latencies);
    } else {
        for (int i = 0; i < num_query; i++) {
            auto q0 = std::chrono::high_resolution_clock::now();
            results[i] = hnsw->searchKnn(&query_data[i * dim], k);
            auto q1 = std::chrono::high_resolution_clock::now();
            latencies[i] = std::chrono::duration<double, std::micro>(q1 - q0).count();
        }
    }
    auto t1 = std::chrono::high_resolution_clock::now();
    double total_s = std::chrono::duration<double>(t1 - t0).count();

    std::sort(latencies.begin(), latencies.end());
    double mean_us = 0;
    for (auto l : latencies) mean_us += l;
    mean_us /= num_query;
    double p50 = latencies[num_query / 2];
    double p95 = latencies[(size_t)(num_query * 0.95)];
    double qps = num_query / total_s;

    size_t correct = 0;
    size_t total = 0;
    for (int i = 0; i < num_query; i++) {
        std::set<uint64_t> gt_set;
        for (size_t j = 0; j < gt_data[i].size() && j < (size_t)k; j++)
            gt_set.insert(gt_data[i][j]);
        size_t found = 0;
        for (const auto& [d, id] : results[i]) {
            if (gt_set.count(id)) found++;
        }
        correct += found;
        total += k;
    }
    double recall = (double)correct / total * 100;

    std::cout << "\n=== Results ===" << std::endl;
    std::cout << "Recall: " << std::fixed << std::setprecision(2) << recall << "%" << std::endl;
    std::cout << "Mean:   " << mean_us / 1000.0 << " ms" << std::endl;
    std::cout << "P50:    " << p50 / 1000.0 << " ms" << std::endl;
    std::cout << "P95:    " << p95 / 1000.0 << " ms" << std::endl;
    std::cout << "QPS:    " << std::fixed << std::setprecision(1) << qps << std::endl;
    std::cout << "RSS:    " << getRSS_MB() << " MB" << std::endl;

    return 0;
}
