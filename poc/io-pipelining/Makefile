# poc/io-pipelining/Makefile - I/O Pipelining POC 构建
CXX = g++
CXXFLAGS = -O3 -std=c++17 -Wall -Wextra -I../../hnswlib -I../../include -I. -march=native
LDFLAGS = -pthread

BUILD_DIR = build
CORE_SRC = ../../src/core/block_cache.cpp ../../src/core/graph_prefetcher.cpp

$(BUILD_DIR)/benchmark_pipe: benchmark_pipe.cpp disk_hnsw_pipe.cpp $(CORE_SRC) disk_hnsw_pipe.h | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ benchmark_pipe.cpp disk_hnsw_pipe.cpp $(CORE_SRC) $(LDFLAGS)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

clean:
	rm -f $(BUILD_DIR)/benchmark_pipe
