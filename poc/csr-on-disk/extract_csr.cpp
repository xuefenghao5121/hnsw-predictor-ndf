// extract_csr.cpp - 从 graph_structure.bin 提取 CSR compact 到独立文件
// 
// 用途: 为 csr-on-disk POC 准备独立的 CSR compact 文件
// 
// 构建: g++ -O2 -std=c++17 -I../../include -o extract_csr extract_csr.cpp
// 用法: ./extract_csr <graph_structure.bin> <output_csr_compact.bin>
//
// 输出文件: 纯压缩字节流 (adj_csr_compact_ 的内容)
// 需配合 adj_csr_byte_offsets_ (保留在内存中) 使用

#include "common.h"
#include <fstream>
#include <iostream>
#include <vector>
#include <cstdint>

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <graph_structure.bin> <output_csr_compact.bin>" << std::endl;
        return 1;
    }

    std::string graph_path = argv[1];
    std::string output_path = argv[2];

    // Load graph using slim_adj (loads L0 adjacency for CSR building)
    std::cout << "Loading graph (slim_adj) from " << graph_path << "..." << std::endl;
    GraphStructure g = load_graph_structure_slim_adj(graph_path);

    uint32_t N = g.num_nodes;
    std::cout << "Graph: " << N << " nodes, dim=" << g.dim << std::endl;

    // Build CSR compact (delta+varint) - same logic as disk_hnsw.cpp:2681
    std::vector<uint8_t> csr_compact;
    csr_compact.reserve(N * 21 * 2);  // estimate

    // Need BFS mapping - load it
    // Actually, the graph_structure.bin already has BFS-remapped adjacency0
    // (adjacency0 is in new_id space after BFS reorder)

    uint32_t total_edges = 0;
    for (uint32_t i = 0; i < N; i++) {
        total_edges += g.adjacency0[i].size();
    }
    std::cout << "Total L0 edges: " << total_edges << std::endl;

    // Build byte_offsets
    std::vector<uint32_t> byte_offsets(N + 1, 0);

    for (uint32_t i = 0; i < N; i++) {
        byte_offsets[i] = (uint32_t)csr_compact.size();

        // Delta encode + varint encode neighbors
        uint32_t prev = 0;
        for (uint32_t neighbor : g.adjacency0[i]) {
            uint32_t delta = neighbor - prev;
            uint8_t buf[5];
            size_t n = varint_encode(delta, buf);
            csr_compact.insert(csr_compact.end(), buf, buf + n);
            prev = neighbor;
        }
    }
    byte_offsets[N] = (uint32_t)csr_compact.size();

    size_t compact_mb = csr_compact.size() / (1024.0 * 1024);
    std::cout << "CSR compact: " << compact_mb << " MB (" << csr_compact.size() << " bytes)" << std::endl;
    std::cout << "Byte offsets: " << (N + 1) * 4 / 1024.0 / 1024 << " MB" << std::endl;
    std::cout << "Compression ratio: " << (double)total_edges * 4 / csr_compact.size() << "x" << std::endl;

    // Write CSR compact to file
    std::ofstream out(output_path, std::ios::binary);
    out.write(reinterpret_cast<const char*>(csr_compact.data()), csr_compact.size());
    out.close();

    std::cout << "Written to: " << output_path << std::endl;

    // Also write byte_offsets (for verification)
    std::string offsets_path = std::string(output_path) + ".offsets";
    std::ofstream off(offsets_path, std::ios::binary);
    off.write(reinterpret_cast<const char*>(byte_offsets.data()), byte_offsets.size() * sizeof(uint32_t));
    off.close();
    std::cout << "Byte offsets written to: " << offsets_path << std::endl;

    return 0;
}
