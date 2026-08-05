# poc/multi-thread-scaling/Makefile
# POC build: compile MT benchmarks against Trunk headers + POC source

CXX = g++
CXXFLAGS = -O3 -std=c++17 -Wall -Wextra -I../../hnswlib -I../../include -march=native
LDFLAGS = -pthread

BUILD_DIR = build

# POC uses modified disk_hnsw_mt.cpp + Trunk's block_cache.cpp + graph_prefetcher.cpp
CORE_SRC = disk_hnsw_mt.cpp ../../src/core/block_cache.cpp ../../src/core/graph_prefetcher.cpp

all: $(BUILD_DIR)/benchmark_diskhnsw_mt $(BUILD_DIR)/benchmark_hnswlib_native_mt

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/benchmark_diskhnsw_mt: benchmark_diskhnsw_mt.cpp $(CORE_SRC) | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ benchmark_diskhnsw_mt.cpp $(CORE_SRC) $(LDFLAGS)

$(BUILD_DIR)/benchmark_hnswlib_native_mt: benchmark_hnswlib_native_mt.cpp | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ benchmark_hnswlib_native_mt.cpp $(LDFLAGS)

clean:
	rm -f $(BUILD_DIR)/*

.PHONY: all clean
