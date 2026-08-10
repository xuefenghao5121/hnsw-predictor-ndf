// build_bfs_csr.cpp - 离线工具：构建 BFS-order 压缩 CSR 文件
//
// 从 graph.bin + bfs.bin 构建 Delta+Varint 压缩 CSR，序列化到文件。
// 输出文件格式: BCSC + N(4B) + compact_size(4B) + offsets_size(4B) + compact_data + offsets_data
//
// 用法: ./build_bfs_csr <graph.bin> <bfs.bin> <output_csr.bin>

#include <cstdio>
#include <cstdint>
#include <cstring>
#include <vector>
#include <fstream>
#include <iostream>
#include <algorithm>

// Must match common.h GraphHeader
#pragma pack(push, 1)
struct GraphHeader {
    uint32_t magic;
    uint32_t version;
    uint32_t num_nodes;
    uint32_t dim;
    uint32_t maxM;
    uint32_t maxM0;
    uint32_t entry_point;
    int32_t  max_level;
    uint32_t data_size;
    uint32_t reserved;
};
#pragma pack(pop)
static_assert(sizeof(GraphHeader) == 40, "");

static constexpr uint32_t MAGIC_GRAPH = 0x47524148; // "GRAH"

// Varint encode
size_t varint_encode(uint32_t val, uint8_t* buf) {
    size_t n = 0;
    while (val >= 0x80) {
        buf[n++] = (val & 0x7F) | 0x80;
        val >>= 7;
    }
    buf[n++] = val;
    return n;
}

int main(int argc, char* argv[]) {
    if (argc != 4) {
        std::cerr << "Usage: " << argv[0] << " <graph.bin> <bfs.bin> <output_csr.bin>\n";
        return 1;
    }

    // 1. Load graph L0 adjacency
    std::ifstream gin(argv[1], std::ios::binary);
    if (!gin.is_open()) { std::cerr << "Cannot open graph\n"; return 1; }

    GraphHeader hdr;
    gin.read(reinterpret_cast<char*>(&hdr), sizeof(GraphHeader));
    if (hdr.magic != MAGIC_GRAPH) { std::cerr << "Bad graph magic\n"; return 1; }
    uint32_t pad;
    gin.read(reinterpret_cast<char*>(&pad), sizeof(uint32_t));  // 4B padding after header

    uint32_t N = hdr.num_nodes;
    std::cout << "Graph: N=" << N << ", dim=" << hdr.dim << ", maxM0=" << hdr.maxM0 << "\n";

    // Skip levels (N * int32)
    gin.seekg(sizeof(GraphHeader) + sizeof(uint32_t) + N * sizeof(int32_t), std::ios::beg);

    // Skip vectors (N * data_size) + labels (N * uint64)
    size_t vec_base = sizeof(GraphHeader) + sizeof(uint32_t) + N * sizeof(int32_t);
    size_t data_size_bytes = (size_t)N * hdr.data_size;
    size_t label_base = vec_base + data_size_bytes;
    size_t adj0_base = label_base + (size_t)N * sizeof(uint64_t);
    gin.seekg(adj0_base);

    // Read L0 adjacency
    std::vector<std::vector<uint32_t>> adj0(N);
    size_t total_edges = 0;
    for (uint32_t i = 0; i < N; i++) {
        uint16_t cnt;
        gin.read(reinterpret_cast<char*>(&cnt), sizeof(uint16_t));
        adj0[i].resize(cnt);
        if (cnt > 0) {
            gin.read(reinterpret_cast<char*>(adj0[i].data()), cnt * sizeof(uint32_t));
            total_edges += cnt;
        }
    }
    gin.close();
    std::cout << "Loaded L0 adjacency: " << total_edges << " edges ("
              << (total_edges * 4 / 1024 / 1024) << "MB)\n";

    // 2. Load BFS mapping
    std::ifstream bin(argv[2], std::ios::binary);
    if (!bin.is_open()) { std::cerr << "Cannot open bfs\n"; return 1; }

    struct BfsHeader { uint32_t magic, num_nodes, entry_point, reserved; } bhdr;
    bin.read(reinterpret_cast<char*>(&bhdr), sizeof(BfsHeader));
    if (bhdr.num_nodes != N) { std::cerr << "N mismatch\n"; return 1; }

    std::vector<uint32_t> old_to_new(N), new_to_old(N);
    bin.read(reinterpret_cast<char*>(old_to_new.data()), N * sizeof(uint32_t));
    bin.read(reinterpret_cast<char*>(new_to_old.data()), N * sizeof(uint32_t));
    bin.close();

    // 3. Build BFS-remapped CSR with Delta+Varint compression
    std::cout << "Building BFS-remapped compressed CSR...\n";

    std::vector<uint8_t> compact;
    compact.reserve(total_edges * 2);
    std::vector<uint32_t> byte_offsets(N + 1);

    uint8_t vbuf[5];
    for (uint32_t new_id = 0; new_id < N; new_id++) {
        byte_offsets[new_id] = (uint32_t)compact.size();
        uint32_t old_id = new_to_old[new_id];
        // Remap neighbors to new_id space and sort
        std::vector<uint32_t> new_neighbors;
        new_neighbors.reserve(adj0[old_id].size());
        for (uint32_t old_nb : adj0[old_id]) {
            new_neighbors.push_back(old_to_new[old_nb]);
        }
        std::sort(new_neighbors.begin(), new_neighbors.end());
        // Delta encode
        uint32_t prev = 0;
        for (uint32_t nid : new_neighbors) {
            uint32_t delta = nid - prev;
            size_t n = varint_encode(delta, vbuf);
            compact.insert(compact.end(), vbuf, vbuf + n);
            prev = nid;
        }
    }
    byte_offsets[N] = (uint32_t)compact.size();

    // Free adjacency
    adj0.clear();
    adj0.shrink_to_fit();

    size_t compact_mb = compact.size() / (1024.0 * 1024);
    size_t offset_mb = (N + 1) * 4 / (1024.0 * 1024);
    std::cout << "CSR: " << total_edges << " edges, compact=" << compact_mb
              << "MB + offsets=" << offset_mb << "MB = " << (compact_mb + offset_mb) << "MB\n";

    // 4. Write output
    std::ofstream out(argv[3], std::ios::binary);
    if (!out.is_open()) { std::cerr << "Cannot open output\n"; return 1; }

    // Header: BCSC + N + compact_size + offsets_size
    const char magic[4] = {'B', 'C', 'S', 'C'};
    out.write(magic, 4);
    out.write(reinterpret_cast<const char*>(&N), sizeof(uint32_t));
    uint32_t compact_size = compact.size();
    uint32_t offsets_size = byte_offsets.size() * sizeof(uint32_t);
    out.write(reinterpret_cast<const char*>(&compact_size), sizeof(uint32_t));
    out.write(reinterpret_cast<const char*>(&offsets_size), sizeof(uint32_t));

    // Data
    out.write(reinterpret_cast<const char*>(compact.data()), compact_size);
    out.write(reinterpret_cast<const char*>(byte_offsets.data()), offsets_size);
    out.close();

    std::cout << "Written: " << argv[3] << " (" << (16 + compact_size + offsets_size) / 1024 / 1024 << "MB)\n";
    return 0;
}
