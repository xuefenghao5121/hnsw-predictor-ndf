// build_bfs_pq.cpp - 离线工具：构建 BFS-order PQ codes 文件
//
// 读取原始 PQ codes 文件（old_id 顺序）+ BFS 映射文件，
// 输出 BFS-reordered PQ codes 文件（new_id 顺序），供 mmap 使用。
//
// 用法: ./build_bfs_pq <pq_codes.bin> <bfs.bin> <output_bfs_pq.bin>
//
// 输出文件格式:
//   magic(4B 'BPQC') + n(8B) + M(4B) + pq_codes(n*M bytes, new_id 顺序)
//   (不含 codebook，codebook 仍从原 PQ 文件加载)

#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <vector>
#include <fstream>
#include <iostream>

int main(int argc, char* argv[]) {
    if (argc != 4) {
        std::cerr << "Usage: " << argv[0] << " <pq_codes.bin> <bfs.bin> <output_bfs_pq.bin>\n";
        return 1;
    }

    const char* pq_path = argv[1];
    const char* bfs_path = argv[2];
    const char* out_path = argv[3];

    // 1. 读取 PQ 文件头 + codebook + codes (old_id 顺序)
    std::ifstream in(pq_path, std::ios::binary);
    if (!in.is_open()) {
        std::cerr << "Cannot open PQ file: " << pq_path << "\n";
        return 1;
    }

    char magic[4];
    in.read(magic, 4);
    if (std::memcmp(magic, "PQCO", 4) != 0) {
        std::cerr << "Invalid PQ magic\n";
        return 1;
    }

    uint64_t n;
    uint32_t M, nbits, dim;
    in.read(reinterpret_cast<char*>(&n), sizeof(uint64_t));
    in.read(reinterpret_cast<char*>(&M), sizeof(uint32_t));
    in.read(reinterpret_cast<char*>(&nbits), sizeof(uint32_t));
    in.read(reinterpret_cast<char*>(&dim), sizeof(uint32_t));

    uint32_t cb_M, cb_K, cb_dsub;
    in.read(reinterpret_cast<char*>(&cb_M), sizeof(uint32_t));
    in.read(reinterpret_cast<char*>(&cb_K), sizeof(uint32_t));
    in.read(reinterpret_cast<char*>(&cb_dsub), sizeof(uint32_t));

    std::cout << "PQ file: N=" << n << ", M=" << M << ", nbits=" << nbits
              << ", dim=" << dim << ", codebook K=" << cb_K << ", dsub=" << cb_dsub << "\n";

    // 跳过 codebook
    size_t codebook_size = (size_t)cb_M * cb_K * cb_dsub;
    in.seekg(codebook_size * sizeof(float), std::ios::cur);

    // 读取 PQ codes (old_id 顺序)
    std::cout << "Reading " << (n * M / 1024 / 1024) << "MB PQ codes (old_id order)...\n";
    std::vector<uint8_t> pq_codes_old(n * M);
    in.read(reinterpret_cast<char*>(pq_codes_old.data()), n * M);
    in.close();

    // 2. 读取 BFS 映射
    // BFS 文件格式: BfsHeader + old_to_new[n] + new_to_old[n]
    // BfsHeader: magic(4B) + num_nodes(4B) + ...
    std::ifstream bfs_in(bfs_path, std::ios::binary);
    if (!bfs_in.is_open()) {
        std::cerr << "Cannot open BFS file: " << bfs_path << "\n";
        return 1;
    }

    // 读 header
    uint32_t bfs_magic, num_nodes;
    bfs_in.read(reinterpret_cast<char*>(&bfs_magic), sizeof(uint32_t));
    bfs_in.read(reinterpret_cast<char*>(&num_nodes), sizeof(uint32_t));
    // 跳过剩余 header (如果有)
    // BfsHeader: magic(4B) + num_nodes(4B) + entry_point(4B) + reserved(4B)
    struct BfsHeader {
        uint32_t magic;
        uint32_t num_nodes;
        uint32_t entry_point;
        uint32_t reserved;
    } bhdr;
    bfs_in.seekg(0, std::ios::beg);
    bfs_in.read(reinterpret_cast<char*>(&bhdr), sizeof(BfsHeader));

    if (bhdr.num_nodes != n) {
        std::cerr << "Node count mismatch: PQ=" << n << " vs BFS=" << bhdr.num_nodes << "\n";
        return 1;
    }
    std::cout << "BFS: " << bhdr.num_nodes << " nodes, max_level=" << bhdr.entry_point << "\n";

    // 读 old_to_new + new_to_old
    std::vector<uint32_t> old_to_new(n), new_to_old(n);
    bfs_in.read(reinterpret_cast<char*>(old_to_new.data()), n * sizeof(uint32_t));
    bfs_in.read(reinterpret_cast<char*>(new_to_old.data()), n * sizeof(uint32_t));
    bfs_in.close();

    // 3. BFS reorder PQ codes
    std::cout << "BFS reordering PQ codes...\n";
    std::vector<uint8_t> pq_codes_bfs(n * M);
    for (uint32_t new_id = 0; new_id < n; new_id++) {
        uint32_t old_id = new_to_old[new_id];
        std::memcpy(&pq_codes_bfs[new_id * M], &pq_codes_old[old_id * M], M);
    }

    // 4. 写输出文件
    std::ofstream out(out_path, std::ios::binary);
    if (!out.is_open()) {
        std::cerr << "Cannot open output: " << out_path << "\n";
        return 1;
    }

    // 写 header: BPQC + n + M
    const char out_magic[4] = {'B', 'P', 'Q', 'C'};
    out.write(out_magic, 4);
    out.write(reinterpret_cast<const char*>(&n), sizeof(uint64_t));
    out.write(reinterpret_cast<const char*>(&M), sizeof(uint32_t));

    // 写 BFS-order PQ codes
    out.write(reinterpret_cast<const char*>(pq_codes_bfs.data()), n * M);
    out.close();

    std::cout << "Written BFS-order PQ codes: " << out_path
              << " (" << (n * M / 1024 / 1024) << "MB + 16B header)\n";
    std::cout << "Done.\n";

    return 0;
}
