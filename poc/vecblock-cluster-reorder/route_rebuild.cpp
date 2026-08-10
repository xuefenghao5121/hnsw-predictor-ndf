// route_rebuild.cpp — rebuild route table for cluster-ordered vecblocks
// POC: vecblock-cluster-reorder
//
// Build: g++ -O3 -std=c++17 route_rebuild.cpp -o build/route_rebuild
//
// Usage:
//   ./route_rebuild <old_route.bin> <old_to_new.bin> <N> <vecs_per_block> <out_route.bin>

#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <vector>
#include <fstream>
#include <iostream>

int main(int argc, char** argv) {
    if (argc < 6) {
        fprintf(stderr, "Usage: %s <old_route.bin> <old_to_new.bin> <N> <vecs_per_block> <out_route.bin>\n", argv[0]);
        return 1;
    }
    const char* old_route = argv[1];
    const char* old_to_new_path = argv[2];
    int N = std::atoi(argv[3]);
    int vpb = std::atoi(argv[4]);  // vecs per block (e.g. 32 for 128-dim, 16 for 256-dim)
    const char* out_route = argv[5];

    // Read old_to_new mapping
    std::vector<uint32_t> old_to_new(N);
    {
        std::ifstream in(old_to_new_path, std::ios::binary);
        if (!in) { fprintf(stderr, "Cannot open %s\n", old_to_new_path); return 1; }
        in.read(reinterpret_cast<char*>(old_to_new.data()), N * sizeof(uint32_t));
    }

    // Build new route table: route[node_id] = new_position / vpb
    std::vector<uint32_t> new_route(N);
    for (int i = 0; i < N; i++) {
        new_route[i] = old_to_new[i] / (uint32_t)vpb;
    }

    // Write
    {
        std::ofstream out(out_route, std::ios::binary);
        out.write(reinterpret_cast<const char*>(new_route.data()), N * sizeof(uint32_t));
        fprintf(stderr, "[RouteRebuild] Wrote %s (%d entries, vpb=%d, %d blocks)\n",
                out_route, N, vpb, (N + vpb - 1) / vpb);
    }
    return 0;
}
