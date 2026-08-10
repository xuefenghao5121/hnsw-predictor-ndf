// cluster_reorder.cpp — R0: within-block k-means cluster sort
// POC: vecblock-cluster-reorder
//
// Reads vecblocks (64KB blocks with BlockHeader + node_ids + vectors),
// clusters vectors via k-means, sorts vectors + node_ids within each block
// by cluster ID. Preserves block boundaries — route table unchanged.
//
// Block format (per block, starts at offset 0 in 64KB block):
//   [0-3]   block_id   (uint32)
//   [4-7]   node_count (uint32)
//   [8-11]  data_offset (uint32)
//   [12-15] flags      (uint32)
//   [16..]  node_ids   (node_count * 4B)
//   [data_offset..]  vectors (node_count * dim * 4B)
//
// Build: g++ -O3 -std=c++17 -march=native -fopenmp cluster_reorder.cpp -o cluster_reorder
// Usage: ./cluster_reorder <vecs.fvecs> <bfs_order.bin> <dim> <in_vecblocks> <out_vecblocks> <k>

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
#include <chrono>

#ifdef _OPENMP
#include <omp.h>
#endif

// ============================================================
// K-Means (k-means++ init, Lloyd iterations)
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
        // k-means++ init
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

        // Lloyd
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
        fprintf(stderr, "Usage: %s <dim> <in_vecblocks> <out_vecblocks> <k>\n", argv[0]);
        return 1;
    }
    uint32_t dim            = (uint32_t)std::atoi(argv[1]);
    const char* in_path     = argv[2];
    const char* out_path    = argv[3];
    int k                   = std::atoi(argv[4]);

    // 1. First pass: extract all vectors from vecblock file for clustering
    fprintf(stderr, "[1] Extracting vectors from vecblocks...\n");
    std::ifstream vb_tmp(in_path, std::ios::binary);
    if (!vb_tmp) { fprintf(stderr, "Cannot open %s\n", in_path); return 1; }
    char tmp_hdr[4096];
    vb_tmp.read(tmp_hdr, 4096);
    uint32_t tmp_magic, tmp_ver, tmp_bs, tmp_nb;
    memcpy(&tmp_magic, tmp_hdr + 0, 4);
    memcpy(&tmp_ver, tmp_hdr + 4, 4);
    memcpy(&tmp_bs, tmp_hdr + 8, 4);
    memcpy(&tmp_nb, tmp_hdr + 12, 4);
    if (tmp_magic != 0x424C4B48) { fprintf(stderr, "Bad magic\n"); return 1; }

    // Count total vectors
    std::vector<char> tmp_block(tmp_bs);
    uint64_t total_N = 0;
    for (uint32_t b = 0; b < tmp_nb; b++) {
        vb_tmp.read(tmp_block.data(), tmp_bs);
        uint32_t cnt; memcpy(&cnt, tmp_block.data() + 4, 4);
        total_N += cnt;
    }
    fprintf(stderr, "[1] Total vectors in file: %lu\n", total_N);

    // Allocate and extract
    std::vector<float> all_vecs(total_N * dim);
    std::vector<uint32_t> global_pos(total_N);  // global_pos[i] = (block_id << 16 | local_offset)
    vb_tmp.clear(); vb_tmp.seekg(4096);
    uint64_t pos = 0;
    for (uint32_t b = 0; b < tmp_nb; b++) {
        vb_tmp.read(tmp_block.data(), tmp_bs);
        uint32_t cnt, data_off;
        memcpy(&cnt, tmp_block.data() + 4, 4);
        memcpy(&data_off, tmp_block.data() + 8, 4);
        const char* vecs = tmp_block.data() + data_off;
        for (uint32_t v = 0; v < cnt; v++) {
            memcpy(all_vecs.data() + pos * dim, vecs + v * dim * 4, dim * 4);
            global_pos[pos] = (b << 16) | v;
            pos++;
        }
    }
    fprintf(stderr, "[1] Extracted %lu vectors\n", total_N);

    // 2. K-Means clustering
    fprintf(stderr, "[2] K-Means k=%d on %lu vectors dim=%d...\n", k, total_N, dim);
    KMeans km;
    auto t0 = std::chrono::high_resolution_clock::now();
    km.fit(all_vecs.data(), total_N, dim, k);
    auto t1 = std::chrono::high_resolution_clock::now();
    double sec = std::chrono::duration<double>(t1 - t0).count();
    fprintf(stderr, "[2] Done in %.1fs. ", sec);
    {
        std::vector<int> cs(k, 0);
        for (size_t i = 0; i < total_N; i++) cs[km.assignments[i]]++;
        int mn = *std::min_element(cs.begin(), cs.end());
        int mx = *std::max_element(cs.begin(), cs.end());
        fprintf(stderr, "Cluster sizes: min=%d max=%d avg=%.0f\n", mn, mx, (float)total_N/k);
    }

    // 4. Read vecblock header (first 4096 bytes)
    fprintf(stderr, "[4] Processing vecblocks...\n");
    std::ifstream vb_in(in_path, std::ios::binary);
    if (!vb_in) { fprintf(stderr, "Cannot open %s\n", in_path); return 1; }
    char file_hdr[4096];
    vb_in.read(file_hdr, 4096);

    // Parse BlocksFileHeader
    uint32_t magic, version, block_size, num_blocks;
    memcpy(&magic, file_hdr + 0, 4);
    memcpy(&version, file_hdr + 4, 4);
    memcpy(&block_size, file_hdr + 8, 4);
    memcpy(&num_blocks, file_hdr + 12, 4);

    size_t vec_bytes = (size_t)dim * sizeof(float);
    uint32_t vpp = 4096 / vec_bytes;
    fprintf(stderr, "[4] blocks=%d block_size=%d dim=%u vec_bytes=%zu vpp=%u\n",
            num_blocks, block_size, dim, vec_bytes, vpp);

    // 5. Within-block cluster sort
    std::ofstream out(out_path, std::ios::binary);
    out.write(file_hdr, 4096);

    std::vector<char> block_buf(block_size);
    std::vector<char> out_buf(block_size);
    uint64_t total_nodes = 0;
    uint64_t total_cluster_switches = 0;

    for (uint32_t b = 0; b < num_blocks; b++) {
        vb_in.read(block_buf.data(), block_size);
        if (!vb_in) { fprintf(stderr, "ERROR: read block %d\n", b); return 1; }

        // Parse per-block header
        uint32_t block_id, cnt, data_offset, flags;
        memcpy(&block_id, block_buf.data() + 0, 4);
        memcpy(&cnt, block_buf.data() + 4, 4);
        memcpy(&data_offset, block_buf.data() + 8, 4);
        memcpy(&flags, block_buf.data() + 12, 4);

        if (cnt == 0) {
            out.write(block_buf.data(), block_size);
            continue;
        }

        // Read node_ids
        std::vector<uint32_t> node_ids(cnt);
        memcpy(node_ids.data(), block_buf.data() + 16, cnt * sizeof(uint32_t));

        // Lookup cluster assignment: this block's vectors correspond to
        // global positions total_nodes .. total_nodes+cnt-1 in the extraction order
        std::vector<int> vec_cluster(cnt);
        for (uint32_t i = 0; i < cnt && (total_nodes + i) < total_N; i++) {
            vec_cluster[i] = km.assignments[total_nodes + i];
        }

        // Sort indices by cluster ID
        std::vector<uint32_t> sorted_idx(cnt);
        std::iota(sorted_idx.begin(), sorted_idx.end(), 0u);
        std::sort(sorted_idx.begin(), sorted_idx.end(),
                  [&](uint32_t a, uint32_t b) { return vec_cluster[a] < vec_cluster[b]; });

        // Count cluster transitions
        int prev_c = -1;
        for (uint32_t i = 0; i < cnt; i++) {
            int c = vec_cluster[sorted_idx[i]];
            if (c != prev_c) { total_cluster_switches++; prev_c = c; }
        }

        // Write: copy block header as-is
        memcpy(out_buf.data(), block_buf.data(), 16);

        // Write reordered node_ids
        for (uint32_t i = 0; i < cnt; i++) {
            uint32_t new_i = sorted_idx[i];
            memcpy(out_buf.data() + 16 + i * 4, &node_ids[new_i], 4);
        }

        // Write reordered vectors
        const char* vec_src = block_buf.data() + data_offset;
        char* vec_dst = out_buf.data() + data_offset;
        for (uint32_t i = 0; i < cnt; i++) {
            uint32_t new_i = sorted_idx[i];
            memcpy(vec_dst + i * vec_bytes, vec_src + new_i * vec_bytes, vec_bytes);
        }

        // Pad to block_size if needed
        size_t used = data_offset + (size_t)cnt * vec_bytes;
        if (used < block_size) memset(out_buf.data() + used, 0, block_size - used);

        out.write(out_buf.data(), block_size);
        total_nodes += cnt;

        if (b % 1000 == 0) fprintf(stderr, "\r[5] block %d/%d nodes=%lu switches=%lu",
                                    b, num_blocks, total_nodes, total_cluster_switches);
    }
    fprintf(stderr, "\r[5] Complete: %d blocks, %lu nodes, %lu cluster switches\n",
            num_blocks, total_nodes, total_cluster_switches);

    fprintf(stderr, "Done. Output: %s\n", out_path);
    return 0;
}
