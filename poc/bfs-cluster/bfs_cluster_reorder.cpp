// bfs_cluster_reorder.cpp — R0: BFS-supervised k-means + within-block cluster sort
// POC: bfs-cluster
//
// Modifies k-means assignment to penalize separation of graph neighbors:
//   assignment(i) = argmin_c [ ||v_i - μ_c||² - λ × N_c(i) ]
// where N_c(i) = # neighbors of i assigned to cluster c
//
// Build: g++ -O3 -std=c++17 -march=native -fopenmp -I../../include bfs_cluster_reorder.cpp -o bfs_cluster_reorder
// Usage: ./bfs_cluster_reorder <dim> <graph.bin> <in_vecblocks> <out_vecblocks> <k> <lambda>

#include "common.h"
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
#include <unordered_map>

#ifdef _OPENMP
#include <omp.h>
#endif

// ============================================================
// BFS-Supervised K-Means
// ============================================================

struct BFSKMeans {
    int k, dim, N;
    std::vector<float> centroids;
    std::vector<int> assignments;
    const std::vector<std::vector<uint32_t>>& adj;  // graph adjacency
    float lambda;  // weight of graph penalty

    BFSKMeans(const std::vector<std::vector<uint32_t>>& adj_, float lambda_)
        : adj(adj_), lambda(lambda_) {}

    // Count neighbors of node i that are in each cluster
    void neighborCounts(int i, const std::vector<int>& cur_assign,
                        std::vector<int>& nbr_counts) const {
        std::fill(nbr_counts.begin(), nbr_counts.end(), 0);
        for (uint32_t nb : adj[i]) {
            if (nb < (uint32_t)cur_assign.size()) {
                nbr_counts[cur_assign[nb]]++;
            }
        }
    }

    void fit(const float* data, int N_, int dim_, int k_, int max_iters = 20, int seed = 42) {
        N = N_; dim = dim_; k = k_;
        centroids.resize(k * dim);
        assignments.resize(N);

        std::mt19937 rng(seed);
        // k-means++ init (standard)
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

        // BFS-supervised Lloyd iterations
        std::vector<float> new_centroids(k * dim);
        std::vector<int> counts(k);
        std::vector<int> nbr_counts(k);  // per-thread buffer

        for (int iter = 0; iter < max_iters; iter++) {
            // BFS-supervised assignment
            long total_graph_bonus = 0;
            #pragma omp parallel private(nbr_counts)
            {
                nbr_counts.resize(k);
                long local_bonus = 0;
                #pragma omp for
                for (int i = 0; i < N; i++) {
                    // BFS supervision: count neighbors per cluster
                    int max_nbr_cluster = -1;
                    int max_nbr_count = 0;
                    if (adj[i].size() > 0) {
                        neighborCounts(i, assignments, nbr_counts);
                        for (int c = 0; c < k; c++) {
                            if (nbr_counts[c] > max_nbr_count) {
                                max_nbr_count = nbr_counts[c];
                                max_nbr_cluster = c;
                            }
                        }
                    }

                    // BFS-supervised distance
                    float best_score = std::numeric_limits<float>::max();
                    int best_c = 0;
                    const float* p = data + i * dim;
                    for (int c = 0; c < k; c++) {
                        float d2 = 0;
                        const float* cc = centroids.data() + c * dim;
                        for (int j = 0; j < dim; j++) {
                            float diff = p[j] - cc[j]; d2 += diff * diff;
                        }
                        // Graph penalty: prefer clusters with more neighbors
                        float score = d2 - lambda * (float)nbr_counts[c];
                        if (score < best_score) { best_score = score; best_c = c; }
                    }
                    assignments[i] = best_c;
                    if (best_c == max_nbr_cluster) local_bonus++;
                }
                #pragma omp atomic
                total_graph_bonus += local_bonus;
            }

            // Update centroids
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
            for (int c = 0; c < k; c++) {
                if (!counts[c]) continue;
                float* nc = new_centroids.data() + c * dim;
                float* oc = centroids.data() + c * dim;
                float shift = 0;
                for (int j = 0; j < dim; j++) {
                    nc[j] /= counts[c];
                    float diff = nc[j] - oc[j];
                    shift += diff * diff; oc[j] = nc[j];
                }
                if (shift > max_shift) max_shift = shift;
            }
            float graph_ratio = N > 0 ? (float)total_graph_bonus / N : 0;
            fprintf(stderr, "\r[BFS-KMeans] iter %d/%d max_shift=%.4f graph_aligned=%.1f%%",
                    iter+1, max_iters, max_shift, graph_ratio * 100);
            if (max_shift < 1e-6f) { fprintf(stderr, " converged\n"); break; }
        }
        fprintf(stderr, "\n");
    }
};

// ============================================================
// Main — same within-block structure as cluster_reorder.cpp
// ============================================================

int main(int argc, char** argv) {
    if (argc < 7) {
        fprintf(stderr, "Usage: %s <dim> <graph.bin> <in_vecblocks> <out_vecblocks> <k> <lambda>\n", argv[0]);
        return 1;
    }
    uint32_t dim        = (uint32_t)std::atoi(argv[1]);
    const char* graph_path = argv[2];
    const char* in_path = argv[3];
    const char* out_path = argv[4];
    int k               = std::atoi(argv[5]);
    float lambda        = (float)std::atof(argv[6]);

    size_t vec_bytes = dim * sizeof(float);

    // 1. Load graph adjacency (slim_adj — only L0 edges)
    fprintf(stderr, "[1] Loading graph adjacency...\n");
    auto graph = load_graph_structure_slim_adj(graph_path);
    uint32_t num_nodes = graph.num_nodes;
    size_t total_edges = 0;
    for (auto& a : graph.adjacency0) total_edges += a.size();
    fprintf(stderr, "[1] Graph: %u nodes, %zu L0 edges\n",
            num_nodes, total_edges);

    // 2. Extract vectors from vecblocks (same as cluster_reorder)
    fprintf(stderr, "[2] Extracting vectors...\n");
    std::ifstream vb_in(in_path, std::ios::binary);
    if (!vb_in) { fprintf(stderr, "Cannot open %s\n", in_path); return 1; }
    char file_hdr[4096];
    vb_in.read(file_hdr, 4096);

    uint32_t magic, version, block_size, num_blocks;
    memcpy(&magic, file_hdr + 0, 4);
    memcpy(&version, file_hdr + 4, 4);
    memcpy(&block_size, file_hdr + 8, 4);
    memcpy(&num_blocks, file_hdr + 12, 4);

    // Count vectors
    std::vector<char> block_buf(block_size);
    uint64_t total_N = 0;
    for (uint32_t b = 0; b < num_blocks; b++) {
        vb_in.read(block_buf.data(), block_size);
        uint32_t cnt; memcpy(&cnt, block_buf.data() + 4, 4);
        total_N += cnt;
    }
    fprintf(stderr, "[2] %lu vectors, blocks=%d\n", total_N, num_blocks);

    // Extract vectors + node_ids
    struct VecInfo { uint32_t node_id; };
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
            memcpy(&all_info[pos].node_id, block_buf.data() + 16 + v * 4, 4);
            memcpy(all_vecs.data() + pos * dim, vecs + v * vec_bytes, vec_bytes);
            pos++;
        }
    }
    fprintf(stderr, "[2] Extracted %lu vectors\n", pos);

    // 3. BFS-supervised K-Means
    fprintf(stderr, "[3] BFS-KMeans k=%d λ=%.1f...\n", k, lambda);
    BFSKMeans km(graph.adjacency0, lambda);
    auto t0 = std::chrono::high_resolution_clock::now();
    km.fit(all_vecs.data(), total_N, dim, k);
    auto t1 = std::chrono::high_resolution_clock::now();
    double sec = std::chrono::duration<double>(t1 - t0).count();
    fprintf(stderr, "[3] Done in %.1fs\n", sec);

    // Cluster stats
    {
        std::vector<int> cs(k, 0);
        for (size_t i = 0; i < total_N; i++) cs[km.assignments[i]]++;
        int mn = *std::min_element(cs.begin(), cs.end());
        int mx = *std::max_element(cs.begin(), cs.end());
        fprintf(stderr, "[3] Cluster sizes: min=%d max=%d avg=%.0f\n", mn, mx, (float)total_N/k);
    }

    // 4. Within-block cluster sort (same as cluster_reorder)
    fprintf(stderr, "[4] Within-block cluster sort...\n");
    std::ofstream out(out_path, std::ios::binary);
    out.write(file_hdr, 4096);
    uint32_t vpp = 4096 / vec_bytes;

    std::vector<char> out_buf(block_size);
    uint64_t global_pos = 0;
    uint64_t total_switches = 0;

    vb_in.clear(); vb_in.seekg(4096);
    for (uint32_t b = 0; b < num_blocks; b++) {
        vb_in.read(block_buf.data(), block_size);
        uint32_t cnt, data_off;
        memcpy(&cnt, block_buf.data() + 4, 4);
        memcpy(&data_off, block_buf.data() + 8, 4);

        if (cnt == 0) { out.write(block_buf.data(), block_size); continue; }

        // Build cluster + local_index list
        std::vector<std::pair<int, uint32_t>> indexed;
        for (uint32_t v = 0; v < cnt; v++) {
            // node_id in vecblock is BFS-order ID = position in vecblocks
            uint32_t bfs_id = global_pos + v;
            if (bfs_id >= total_N) break;
            indexed.push_back({km.assignments[bfs_id], v});
        }

        // Count cluster switches
        int prev_c = -1;
        for (auto& [c, off] : indexed) {
            if (c != prev_c) { total_switches++; prev_c = c; }
        }

        // Sort by cluster ID
        std::sort(indexed.begin(), indexed.end(),
                  [](const auto& a, const auto& b) { return a.first < b.first; });

        // Write reordered
        const char* vec_src = block_buf.data() + data_off;
        char* vec_dst = out_buf.data() + data_off;
        memcpy(out_buf.data(), block_buf.data(), 16);  // header
        for (int i = 0; i < (int)indexed.size(); i++) {
            uint32_t new_i = indexed[i].second;
            uint32_t nid;
            memcpy(&nid, block_buf.data() + 16 + new_i * 4, 4);
            memcpy(out_buf.data() + 16 + i * 4, &nid, 4);
            memcpy(vec_dst + i * vec_bytes, vec_src + new_i * vec_bytes, vec_bytes);
        }
        size_t used = data_off + (size_t)cnt * vec_bytes;
        if (used < block_size) memset(out_buf.data() + used, 0, block_size - used);

        out.write(out_buf.data(), block_size);
        global_pos += cnt;
        if (b % 1000 == 0) fprintf(stderr, "\r[4] block %d/%d", b, num_blocks);
    }
    fprintf(stderr, "\r[4] Complete: %lu switches\n", total_switches);

    fprintf(stderr, "Done. Output: %s\n", out_path);
    return 0;
}
