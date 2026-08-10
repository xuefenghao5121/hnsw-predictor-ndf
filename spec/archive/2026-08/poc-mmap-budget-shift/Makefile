CXX = g++
CXXFLAGS = -O3 -std=c++17 -Wall -Wextra -I../../hnswlib -I../../include -I. -march=native
LDFLAGS = -pthread

BUILD_DIR = build

# Offline tool: build BFS-order PQ codes file
$(BUILD_DIR)/build_bfs_pq: build_bfs_pq.cpp | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ $< $(LDFLAGS)

# Offline tool: build BFS-order compressed CSR file
$(BUILD_DIR)/build_bfs_csr: build_bfs_csr.cpp | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ $< $(LDFLAGS)

# mmap benchmark (uses disk_hnsw_mmap.cpp with mmap PQ support)
CORE_SRC = disk_hnsw_mmap.cpp block_cache.cpp ../../src/core/graph_prefetcher.cpp
HEADERS = disk_hnsw_mmap.h block_cache.h common.h layout_provider.h replacement_policy.h graph_prefetcher.h io_uring_wrapper.h

$(BUILD_DIR)/benchmark_mmap: benchmark_mmap.cpp $(CORE_SRC) $(HEADERS) | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ benchmark_mmap.cpp $(CORE_SRC) $(LDFLAGS)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

all: $(BUILD_DIR)/build_bfs_pq $(BUILD_DIR)/build_bfs_csr $(BUILD_DIR)/benchmark_mmap

clean:
	rm -f $(BUILD_DIR)/*

.PHONY: all clean
