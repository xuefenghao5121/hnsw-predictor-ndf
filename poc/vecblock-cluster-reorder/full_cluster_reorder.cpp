// full_cluster_reorder.cpp — R1: full cluster reorder (cross-block)
// POC: vecblock-cluster-reorder
//
// 替代 within-block sort，做全局 cluster 重排：
// 1. 从 vecblock 提取所有 vector + node_id
// 2. k-means 聚类
// 3. 全局按 cluster ID 排序（跨 block）
// 4. 写新 vecblock + 新 route table
//
// Build: g++ -O3 -std=c++17 -march=native -fopenmp full_cluster_reorder.cpp -o full_cluster_reorder
// Usage: ./full_cluster_reorder <dim> <in_vecblocks> <out_dir> <k>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <vector>
#include <algorithm>
#include <numeric>
#include <random>
#include <limits>
#include <cmath>
#include <fstream>
#include <iostream>
#include <chrono>

#ifdef _OPENMP
#include <omp.h>
#endif

// ============================================================
// K-Means (same as cluster_reorder.cpp)
// ============================================================

struct KMeans {
    int k, dim, N;
    std::vector<float> centroids;
    std::vector<int> assignments;

    void fit(const float* data, int N_, int dim_, int k_, int max_iters = 20, int seed = 42) {
        N = N_; dim = dim_; k = k_;
        centroids.resize(k * dim);
        assignments.resize(N);

        std::mt19937 rng(seed);
        {
            std::uniform_int_distribution<int> dist(0, N - 1);
            int first = dist(rng);
            std::copy(data + first * dim, data + first * dim + dim, centroids.begin());
            std::vector<float> min_dist(N, std::numeric_limits<float>::max());
            for (int c = 1; c < k; c++) {
                #pragma omp parallel for
                for (int i = 0; i < N; i++) {
                    float d2 = 0;
                    const float* p = data + i * dim;
                    const float* cc = centroids.data() + (c - 1) * dim;
                    for (int j = 0; j < dim; j++) {
                        float diff = p[j] - cc[j]; d2 += diff * diff;
                    }
                    if (d2 < min_dist[i]) min_dist[i] = d2;
                }
                std::discrete_distribution<int> weighted(min_dist.begin(), min_dist.end());
                int next = weighted(rng);
                std::copy(data + next * dim, data + next * dim + dim, centroids.begin() + c * dim);
            }
        }

        std::vector<float> new_centroids(k * dim);
        std::vector<int> counts(k);
        for (int iter = 0; iter < max_iters; iter++) {
            #pragma omp parallel for
            for (int i = 0; i < N; i++) {
                float best = std::numeric_limits<float>::max();
                int best_c = 0;
                const float* p = data + i * dim;
                for (int c = 0; c < k; c++) {
                    float d2 = 0;
                    const float* cc = centroids.data() + c * dim;
                    for (int j = 0; j < dim; j++) {
                        float diff = p[j] - cc[j]; d2 += diff * diff;
                    }
                    if (d2 < best) { best = d2; best_c = c; }
                }
                assignments[i] = best_c;
            }

            std::fill(new_centroids.begin(), new_centroids.end(), 0.0f);
            std::fill(counts.begin(), counts.end(), 0);
            #pragma omp parallel for
            for (int i = 0; i < N; i++) {
                int c = assignments[i];
                const float* p = data + i * dim;
                #pragma omp critical
                { for (int j = 0; j < dim; j++) new_centroids[c*dim+j] += p[j]; counts[c]++; }
            }
            float max_shift = 0;
            for (int cc = 0; cc < k; cc++) {
                if (!counts[cc]) continue;
                float* nc = new_centroids.data() + cc * dim;
                float* oc = centroids.data() + cc * dim;
                float shift = 0;
                for (int j = 0; j < dim; j++) {
                    nc[j] /= counts[cc];
                    float diff = nc[j] - oc[j];
                    shift += diff * diff; oc[j] = nc[j];
                }
                if (shift > max_shift) max_shift = shift;
            }
            fprintf(stderr, "\r[KMeans] iter %d/%d max_shift=%.6f", iter+1, max_iters, max_shift);
            if (max_shift < 1e-6f) { fprintf(stderr, " converged\n"); break; }
        }
        fprintf(stderr, "\n");
    }
};

// ============================================================
// Main
// ============================================================

int main(int argc, char** argv) {
    if (argc < 5) {
        fprintf(stderr, "Usage: %s <dim> <in_vecblocks> <out_dir> <k>\n", argv[0]);
        return 1;
    }
    uint32_t dim        = (uint32_t)std::atoi(argv[1]);
    const char* in_path = argv[2];
    const char* out_dir = argv[3];
    int k               = std::atoi(argv[4]);

    size_t vec_bytes = (size_t)dim * sizeof(float);

    // 1. Extract all vectors + node_ids from vecblocks
    fprintf(stderr, "[1] Extracting vectors...\n");
    std::ifstream vb_in(in_path, std::ios::binary);
    if (!vb_in) { fprintf(stderr, "Cannot open %s\n", in_path); return 1; }

    char file_hdr[4096];
    vb_in.read(file_hdr, 4096);
    uint32_t magic, version, block_size, num_blocks;
    memcpy(&magic, file_hdr + 0, 4);
    memcpy(&version, file_hdr + 4, 4);
    memcpy(&block_size, file_hdr + 8, 4);
    memcpy(&num_blocks, file_hdr + 12, 4);
    if (magic != 0x424C4B48) { fprintf(stderr, "Bad magic\n"); return 1; }
    fprintf(stderr, "[1] blocks=%d block_size=%d dim=%d\n", num_blocks, block_size, dim);

    // Single-pass: count first, then pre-allocate, then extract
    std::vector<char> block_buf(block_size);
    struct VecInfo { uint32_t node_id; };
    uint64_t total_N = 0;

    // Pass 1: count
    for (uint32_t b = 0; b < num_blocks; b++) {
        vb_in.read(block_buf.data(), block_size);
        uint32_t cnt;
        memcpy(&cnt, block_buf.data() + 4, 4);
        total_N += cnt;
    }
    fprintf(stderr, "[1] %lu vectors total\n", total_N);

    // Pass 2: extract
    std::vector<VecInfo> all_info(total_N);
    std::vector<float> all_vecs(total_N * dim);
    vb_in.clear(); vb_in.seekg(4096);
    uint64_t pos = 0;
    for (uint32_t b = 0; b < num_blocks; b++) {
        vb_in.read(block_buf.data(), block_size);
        uint32_t cnt, data_off;
        memcpy(&cnt, block_buf.data() + 4, 4);
        memcpy(&data_off, block_buf.data() + 8, 4);
        const char* vecs = block_buf.data() + data_off;
        for (uint32_t v = 0; v < cnt; v++) {
            uint32_t nid;
            memcpy(&nid, block_buf.data() + 16 + v * 4, 4);
            all_info[pos].node_id = nid;
            memcpy(all_vecs.data() + pos * dim, vecs + v * vec_bytes, vec_bytes);
            pos++;
        }
    }
    fprintf(stderr, "[1] %lu vectors extracted\n", pos);

    // 2. K-Means
    fprintf(stderr, "[2] K-Means k=%d on %lu vectors...\n", k, total_N);
    KMeans km;
    auto t0 = std::chrono::high_resolution_clock::now();
    km.fit(all_vecs.data(), total_N, dim, k);
    auto t1 = std::chrono::high_resolution_clock::now();
    double sec = std::chrono::duration<double>(t1 - t0).count();
    fprintf(stderr, "[2] Done in %.1fs\n", sec);

    // 3. Global sort: by cluster ID, then by node_id within cluster
    fprintf(stderr, "[3] Global cluster sort...\n");
    std::vector<uint64_t> sorted_idx(total_N);
    std::iota(sorted_idx.begin(), sorted_idx.end(), 0ULL);
    std::sort(sorted_idx.begin(), sorted_idx.end(), [&](uint64_t a, uint64_t b) {
        int ca = km.assignments[a], cb = km.assignments[b];
        if (ca != cb) return ca < cb;          // primary: cluster
        return all_info[a].node_id < all_info[b].node_id;  // secondary: node_id
    });

    // Build: new_position → old_position, and route table (node_id → new_block_id)
    // vectors per block: header(16) + node_ids(vpb*4) + vectors(vpb*vec_bytes) <= block_size
    // vpb = (block_size - 16) / (4 + vec_bytes) = 65520 / 516 = 126 (SIFT 128D)
    uint32_t vpb = (block_size - 16) / (4 + vec_bytes);
    uint32_t new_num_blocks = (total_N + vpb - 1) / vpb;
    fprintf(stderr, "[3] vpb=%d blocks=%d\n", vpb, new_num_blocks);
    std::vector<uint32_t> route(total_N, 0);  // route[node_id] = new_block_id

    for (uint64_t new_pos = 0; new_pos < total_N; new_pos++) {
        uint64_t old_pos = sorted_idx[new_pos];
        uint32_t nid = all_info[old_pos].node_id;
        if (nid >= total_N) {
            fprintf(stderr, "WARN: node_id %u >= %lu at pos %lu\n", nid, total_N, new_pos);
            continue;
        }
        route[nid] = new_pos / vpb;
    }

    // 4. Write new vecblocks
    fprintf(stderr, "[4] Writing new vecblocks (%d blocks)...\n", new_num_blocks);
    std::string out_path = std::string(out_dir) + "/vecblocks_64k.bin";
    std::ofstream out(out_path, std::ios::binary);

    // Copy header, update num_blocks
    memcpy(file_hdr + 12, &new_num_blocks, 4);
    out.write(file_hdr, 4096);

    std::vector<char> out_block(block_size);
    uint64_t written = 0;
    for (uint32_t new_block = 0; new_block < new_num_blocks; new_block++) {
        uint32_t start_v = new_block * vpb;
        uint32_t cnt = std::min((uint64_t)vpb, total_N - start_v);
        uint32_t data_off = 16 + vpb * 4;  // reserve max room for node_ids

        memset(out_block.data(), 0, block_size);
        // BlockHeader
        memcpy(out_block.data() + 0, &new_block, 4);     // block_id
        memcpy(out_block.data() + 4, &cnt, 4);            // node_count
        memcpy(out_block.data() + 8, &data_off, 4);       // data_offset
        uint32_t flags = 2;  // FLAG_VEC_ONLY
        memcpy(out_block.data() + 12, &flags, 4);

        // node_ids
        for (uint32_t v = 0; v < cnt; v++) {
            uint64_t old_pos = sorted_idx[start_v + v];
            uint32_t nid = all_info[old_pos].node_id;
            memcpy(out_block.data() + 16 + v * 4, &nid, 4);
        }

        // vectors
        char* vec_dst = out_block.data() + data_off;
        for (uint32_t v = 0; v < cnt; v++) {
            uint64_t old_pos = sorted_idx[start_v + v];
            memcpy(vec_dst + v * vec_bytes,
                   all_vecs.data() + old_pos * dim, vec_bytes);
        }

        out.write(out_block.data(), block_size);
        written += cnt;
        if (new_block % 1000 == 0) fprintf(stderr, "\r[4] block %d/%d", new_block, new_num_blocks);
    }
    out.flush();
    out.close();
    fprintf(stderr, "\r[4] Complete: %d blocks, %lu vectors\n", new_num_blocks, written);

    // 5. Write route table
    std::string route_path = std::string(out_dir) + "/vec_route.bin";
    {
        std::ofstream rout(route_path, std::ios::binary);
        rout.write(reinterpret_cast<const char*>(route.data()), total_N * sizeof(uint32_t));
        fprintf(stderr, "[5] Route table: %s (%lu entries)\n", route_path.c_str(), total_N);
    }

    // 6. Stats
    {
        std::vector<int> cs(k, 0);
        for (uint64_t i = 0; i < total_N; i++) cs[km.assignments[i]]++;
        int mn = *std::min_element(cs.begin(), cs.end());
        int mx = *std::max_element(cs.begin(), cs.end());
        fprintf(stderr, "[Stats] Cluster sizes: min=%d max=%d avg=%.0f\n", mn, mx, (float)total_N/k);
        fprintf(stderr, "[Stats] vpb=%d blocks=%d route_entries=%lu\n", vpb, new_num_blocks, total_N);
    }

    fprintf(stderr, "Done. Output: %s\n", out_dir);
    return 0;
}
