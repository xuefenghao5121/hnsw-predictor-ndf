// cluster_reorder.cpp — R0: within-block k-means cluster sort
// POC: vecblock-cluster-reorder
//
// Reads existing 64KB-block vecblocks, clusters vectors with k-means,
// sorts vectors within each block by cluster ID (cluster-local ordering),
// writes new vecblock with same header format.
//
// Key: block boundaries preserved → no route table rebuild needed.
//      Only vector order within each block changes.
//
// Build: g++ -O3 -std=c++17 -march=native -fopenmp cluster_reorder.cpp -o cluster_reorder
//
// Usage:
//   ./cluster_reorder <vecs.fvecs> <bfs_order.bin> <in_vecblocks> <out_vecblocks> <k> [dim]

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
#include <unordered_map>

#ifdef _OPENMP
#include <omp.h>
#endif

// Block file header (matches include/common.h BlocksFileHeader)
static constexpr uint32_t MAGIC_BLOCKS = 0x424C4B48;

struct BlocksFileHeader {
    uint32_t magic;
    uint32_t version;
    uint32_t block_size;
    uint32_t num_blocks;
    uint64_t num_vectors;
    uint32_t dim;
    uint32_t reserved[256 - 6];
};

// ============================================================
// K-Means (minimal, k-means++ init, Lloyd)
// ============================================================

struct KMeans {
    int k, dim, N;
    std::vector<float> centroids;
    std::vector<int> assignments;
    float inertia;

    void fit(const float* data, int N_, int dim_, int k_, int max_iters = 20, int seed = 42) {
        N = N_; dim = dim_; k = k_;
        centroids.resize(k * dim);
        assignments.resize(N);

        std::mt19937 rng(seed);
        // k-means++ init
        {
            std::uniform_int_distribution<int> dist(0, N - 1);
            int first = dist(rng);
            std::copy(data + first * dim, data + first * dim + dim, centroids.begin());

            std::vector<float> min_dist(N, std::numeric_limits<float>::max());
            for (int c = 1; c < k; c++) {
                #pragma omp parallel for if(N > 10000)
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

        // Lloyd
        std::vector<float> new_centroids(k * dim);
        std::vector<int> counts(k);
        for (int iter = 0; iter < max_iters; iter++) {
            #pragma omp parallel for if(N > 10000)
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
            #pragma omp parallel for if(N > 10000)
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
            fprintf(stderr, "\r[KMeans] iter %d/%d max_shift=%.6f", iter+1, max_iters, max_shift);
            if (max_shift < 1e-6f) { fprintf(stderr, " converged\n"); break; }
        }
        fprintf(stderr, "\n");

        // Inertia
        inertia = 0;
        for (int i = 0; i < N; i++) {
            const float* p = data + i*dim, *cc = centroids.data() + assignments[i]*dim;
            float d2 = 0;
            for (int j = 0; j < dim; j++) { float diff = p[j]-cc[j]; d2 += diff*diff; }
            inertia += d2;
        }
        inertia /= N;
    }
};

// ============================================================
// Main
// ============================================================

int main(int argc, char** argv) {
    if (argc < 6) {
        fprintf(stderr, "Usage: %s <vecs.fvecs> <bfs_order.bin> <in_vecblocks> <out_vecblocks> <k>\n", argv[0]);
        return 1;
    }
    const char* vecs_path = argv[1];
    const char* bfs_path = argv[2];
    const char* in_path = argv[3];
    const char* out_path = argv[4];
    int k = std::atoi(argv[5]);

    // 1. Read fvecs
    fprintf(stderr, "[1] Loading vectors...\n");
    std::ifstream vin(vecs_path, std::ios::binary);
    if (!vin) { fprintf(stderr, "Cannot open %s\n", vecs_path); return 1; }
    int dim_raw; vin.read(reinterpret_cast<char*>(&dim_raw), 4);
    vin.seekg(0, std::ios::end); size_t fsz = vin.tellg();
    int N = (fsz - 4) / (4 + dim_raw * 4);
    vin.seekg(0);

    std::vector<float> vecs(N * dim_raw);
    for (int i = 0; i < N; i++) {
        int d; vin.read(reinterpret_cast<char*>(&d), 4);
        vin.read(reinterpret_cast<char*>(&vecs[i * dim_raw]), dim_raw * sizeof(float));
    }
    fprintf(stderr, "[1] Loaded %d vectors, dim=%d\n", N, dim_raw);

    // 2. Read BFS order (maps BFS_id → original_id)
    std::vector<uint32_t> bfs_order(N);
    {
        std::ifstream in(bfs_path, std::ios::binary);
        if (!in) { fprintf(stderr, "Cannot open %s\n", bfs_path); return 1; }
        in.read(reinterpret_cast<char*>(bfs_order.data()), N * sizeof(uint32_t));
    }
    fprintf(stderr, "[2] BFS order loaded\n");

    // 3. Read vecblock header
    fprintf(stderr, "[3] Reading vecblock header...\n");
    std::ifstream vinb(in_path, std::ios::binary);
    if (!vinb) { fprintf(stderr, "Cannot open %s\n", in_path); return 1; }
    char hdr[4096];
    vinb.read(hdr, 4096);
    BlocksFileHeader fhdr;
    memcpy(&fhdr, hdr, sizeof(BlocksFileHeader));
    if (fhdr.magic != MAGIC_BLOCKS) {
        fprintf(stderr, "ERROR: bad magic 0x%X (expected 0x%X)\n", fhdr.magic, MAGIC_BLOCKS);
        return 1;
    }
    uint32_t block_size = fhdr.block_size;
    uint32_t num_blocks = fhdr.num_blocks;
    size_t vec_bytes = (size_t)fhdr.dim * sizeof(float);
    uint32_t vpb = block_size / vec_bytes;   // vectors per block
    fprintf(stderr, "[3] blocks=%d block_size=%d dim=%d vpb=%d\n",
            num_blocks, block_size, fhdr.dim, vpb);

    // 4. K-means clustering on BFS-ordered vectors
    fprintf(stderr, "[4] K-Means k=%d...\n", k);
    KMeans km;
    km.fit(vecs.data(), N, dim_raw, k);
    fprintf(stderr, "[4] Done. Inertia=%.2f\n", km.inertia);
    // Cluster size stats
    {
        std::vector<int> cs(k, 0);
        for (int i = 0; i < N; i++) cs[km.assignments[i]]++;
        int mn = *std::min_element(cs.begin(), cs.end());
        int mx = *std::max_element(cs.begin(), cs.end());
        fprintf(stderr, "[4] Cluster sizes: min=%d max=%d avg=%.0f\n", mn, mx, (float)N/k);
    }

    // 5. Within-block cluster sort
    fprintf(stderr, "[5] Within-block cluster sort...\n");
    std::ofstream out(out_path, std::ios::binary);
    out.write(hdr, 4096);  // copy header

    std::vector<char> block_buf(block_size);
    std::vector<char> out_buf(block_size);
    int total_pages = 0;

    for (uint32_t b = 0; b < num_blocks; b++) {
        vinb.read(block_buf.data(), block_size);

        // Each vector in block corresponds to a BFS-order ID
        // bfs_order[new_id] = old_id, where new_id = b * vpb + offset
        // Get cluster assignments for vectors in this block
        std::vector<std::pair<int, int>> vec_cluster;  // (cluster, offset)
        vec_cluster.reserve(vpb);
        for (uint32_t v = 0; v < vpb; v++) {
            uint32_t bfs_id = b * vpb + v;
            if (bfs_id >= (uint32_t)N) break;
            uint32_t orig_id = bfs_order[bfs_id];
            vec_cluster.push_back({km.assignments[orig_id], (int)v});
        }

        // Sort by cluster ID
        std::sort(vec_cluster.begin(), vec_cluster.end(),
                  [](const auto& a, const auto& b) { return a.first < b.first; });

        // Count cluster transitions (= page breaks per block)
        int prev_c = -1;
        for (auto& [c, off] : vec_cluster) {
            if (c != prev_c) { total_pages++; prev_c = c; }
        }

        // Write reordered vectors
        for (int i = 0; i < (int)vec_cluster.size(); i++) {
            int orig_offset = vec_cluster[i].second;
            memcpy(out_buf.data() + i * vec_bytes,
                   block_buf.data() + orig_offset * vec_bytes, vec_bytes);
        }
        // Fill tail of block with zeros (partial last block)
        if (vec_cluster.size() < vpb) {
            memset(out_buf.data() + vec_cluster.size() * vec_bytes, 0,
                   (vpb - vec_cluster.size()) * vec_bytes);
        }
        out.write(out_buf.data(), block_size);

        if (b % 1000 == 0) fprintf(stderr, "\r[5] block %d/%d", b, num_blocks);
    }
    fprintf(stderr, "\r[5] %d blocks processed, ~%d cluster switch pages\n",
            num_blocks, total_pages);

    fprintf(stderr, "Done. Output: %s\n", out_path);
    return 0;
}
