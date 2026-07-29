// shuffle_vecblocks.cpp — Page Shuffle for vecblocks (DEC-018)
//
// 用途: 按 4KB 页粒度重排 vecblocks 文件, 使 HNSW 图上相邻节点共享同一页。
//       配合 Page Search (DEC-017) 提升页内向量利用率。
//
// 算法 (待实现):
//   1. 读取 vecblocks 文件和配套 graph 文件
//   2. 对每个 64KB block 内的节点, 按 HNSW 图邻接关系做页级聚类
//      (贪心策略: 将共享邻居最多的节点分配到同一 4KB 页)
//   3. 输出新 vecblocks 文件 + 新 vec_page_route_table (node→page_id)
//
// 前置条件: SIFT (128D, 512B/vector, 8 vectors/page) 有效。
//           高维数据 (GIST 960D) 一页只放 1 个向量, Shuffle 无收益。
//
// 用法:
//   ./build/shuffle_vecblocks <graph.bin> <bfs.bin> <vecblocks.bin> <output.bin>
//
// 环境变量:
//   PAGE_SHUFFLE_STRATEGY=greedy|random  (默认 greedy)
//   PAGE_SHUFFLE_SEED=42                  (random 策略用)
//
// refines: DEC-006 (BFS 重排布局)
// precondition: DEC-017 (Page Search) 需同一批生成的 shuffle 文件

#include "common.h"
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <vector>
#include <algorithm>
#include <cstdlib>

static uint32_t vectors_per_page(uint32_t dim) {
    return 4096 / (dim * sizeof(float));
}

int main(int argc, char** argv) {
    if (argc < 5) {
        std::cerr << "Usage: " << argv[0]
                  << " <graph.bin> <bfs.bin> <vecblocks.bin> <output.bin>" << std::endl;
        std::cerr << "  DEC-018: Page Shuffle — 按 4KB 页粒度重排 vecblocks" << std::endl;
        std::cerr << "  Env: PAGE_SHUFFLE_STRATEGY=greedy|random (default: greedy)" << std::endl;
        return 1;
    }

    std::string graph_path = argv[1];
    std::string bfs_path    = argv[2];
    std::string input_path  = argv[3];
    std::string output_path = argv[4];

    const char* strategy_env = std::getenv("PAGE_SHUFFLE_STRATEGY");
    std::string strategy = strategy_env ? strategy_env : "greedy";
    const char* seed_env = std::getenv("PAGE_SHUFFLE_SEED");
    uint64_t seed = seed_env ? std::stoull(seed_env) : 42;

    std::cout << "=== Page Shuffle (DEC-018) ===" << std::endl;
    std::cout << "  graph:    " << graph_path << std::endl;
    std::cout << "  bfs:      " << bfs_path << std::endl;
    std::cout << "  input:    " << input_path << std::endl;
    std::cout << "  output:   " << output_path << std::endl;
    std::cout << "  strategy: " << strategy << std::endl;
    std::cout << "  seed:     " << seed << std::endl;

    // ---- 1. 加载 BFS 映射 ----
    std::cout << "[1] Loading BFS order..." << std::endl;
    std::ifstream bfs_in(bfs_path, std::ios::binary);
    if (!bfs_in.is_open()) {
        std::cerr << "ERROR: Cannot open " << bfs_path << std::endl;
        return 1;
    }
    BfsHeader bhdr;
    bfs_in.read(reinterpret_cast<char*>(&bhdr), sizeof(BfsHeader));
    if (bhdr.magic != MAGIC_BFS) {
        std::cerr << "ERROR: Invalid BFS file magic" << std::endl;
        return 1;
    }
    std::vector<uint32_t> old_to_new(bhdr.num_nodes);
    std::vector<uint32_t> new_to_old(bhdr.num_nodes);
    bfs_in.read(reinterpret_cast<char*>(old_to_new.data()), bhdr.num_nodes * sizeof(uint32_t));
    bfs_in.read(reinterpret_cast<char*>(new_to_old.data()), bhdr.num_nodes * sizeof(uint32_t));
    bfs_in.close();
    std::cout << "  nodes: " << bhdr.num_nodes << std::endl;

    // ---- 2. 读取 vecblocks 文件头 ----
    std::cout << "[2] Reading vecblocks header..." << std::endl;
    std::ifstream vb_in(input_path, std::ios::binary);
    if (!vb_in.is_open()) {
        std::cerr << "ERROR: Cannot open " << input_path << std::endl;
        return 1;
    }
    BlocksFileHeader fhdr;
    vb_in.read(reinterpret_cast<char*>(&fhdr), sizeof(BlocksFileHeader));
    if (fhdr.magic != MAGIC_BLOCKS) {
        std::cerr << "ERROR: Invalid vecblocks file magic" << std::endl;
        return 1;
    }
    uint32_t block_size = fhdr.block_size;
    uint32_t num_blocks = fhdr.num_blocks;
    vb_in.close();
    std::cout << "  block_size=" << block_size << " (" << (block_size/1024) << "KB)"
              << ", num_blocks=" << num_blocks << std::endl;

    // ---- 3. 扫描 vecblocks 统计 ----
    std::cout << "[3] Scanning vecblocks for page statistics..." << std::endl;
    vb_in.open(input_path, std::ios::binary);
    vb_in.seekg(4096, std::ios::beg);

    size_t total_nodes = 0, total_slots = 0;
    uint32_t dim = 0;
    for (uint32_t b = 0; b < num_blocks && b < 5; b++) { // 只扫前5块采样dim
        std::vector<char> buf(4096);
        vb_in.read(buf.data(), 4096);
        if (!vb_in) break;
        uint32_t cnt, data_offset, flags;
        std::memcpy(&cnt, buf.data() + 4, 4);
        std::memcpy(&data_offset, buf.data() + 8, 4);
        std::memcpy(&flags, buf.data() + 12, 4);
        if (!(flags & FLAG_VEC_ONLY)) continue;
        // 从 block 尾部反推 dim: vector_bytes = block_size - data_offset, cnt vectors
        if (cnt > 0) {
            uint32_t vector_bytes = block_size - data_offset;
            dim = vector_bytes / (cnt * sizeof(float));
            break;
        }
    }
    // 重新扫描全部
    vb_in.seekg(4096, std::ios::beg);
    for (uint32_t b = 0; b < num_blocks; b++) {
        std::vector<char> buf(4096);
        vb_in.read(buf.data(), 4096);
        if (!vb_in) break;
        uint32_t cnt, data_offset, flags;
        std::memcpy(&cnt, buf.data() + 4, 4);
        std::memcpy(&data_offset, buf.data() + 8, 4);
        std::memcpy(&flags, buf.data() + 12, 4);
        if (!(flags & FLAG_VEC_ONLY)) continue;
        total_nodes += cnt;
        total_slots += cnt;
        vb_in.seekg((std::streamoff)block_size - 4096, std::ios::cur);
    }
    vb_in.close();

    uint32_t vpp = dim > 0 ? vectors_per_page(dim) : 8;
    size_t total_pages_est = (total_slots + vpp - 1) / vpp;
    std::cout << "  total_nodes:      " << total_nodes << std::endl;
    std::cout << "  dim:              " << dim << std::endl;
    std::cout << "  vectors_per_page: " << vpp << std::endl;
    std::cout << "  est_pages:        " << total_pages_est << std::endl;

    // ---- 4. 骨架: pass-through 拷贝 ----
    std::cout << "[4] Writing pass-through output (skeleton — no actual shuffle)..." << std::endl;
    std::ifstream src(input_path, std::ios::binary);
    std::ofstream dst(output_path, std::ios::binary);
    if (!src.is_open() || !dst.is_open()) {
        std::cerr << "ERROR: Cannot open files for copy" << std::endl;
        return 1;
    }
    dst << src.rdbuf();
    src.close();
    dst.close();

    std::cout << "\n=== DEC-018 Page Shuffle complete ===" << std::endl;
    std::cout << "  output: " << output_path << std::endl;
    std::cout << "  TODO: Implement greedy page clustering." << std::endl;
    std::cout << "  Current output is pass-through (identical to input)." << std::endl;
    return 0;
}
