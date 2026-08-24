# POC Makefile - perf-gap-4t (D3+D4)
CXX = g++
CXXFLAGS = -O3 -std=c++17 -Wall -Wextra -I../../hnswlib -I../../include -march=native
LDFLAGS = -pthread

BUILD_DIR = build
ROOT = ../..

# POC 使用修改的副本，但链接原项目的其他源文件
CORE_SRC = disk_hnsw_poc.cpp $(ROOT)/src/core/block_cache.cpp $(ROOT)/src/core/graph_prefetcher.cpp
HEADERS = disk_hnsw_poc.h $(ROOT)/include/block_cache.h $(ROOT)/include/graph_prefetcher.h $(ROOT)/include/layout_provider.h

all: $(BUILD_DIR)/benchmark_poc

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/benchmark_poc: benchmark_poc.cpp $(CORE_SRC) $(HEADERS) | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ benchmark_poc.cpp disk_hnsw_poc.cpp $(ROOT)/src/core/block_cache.cpp $(ROOT)/src/core/graph_prefetcher.cpp $(LDFLAGS)

clean:
	rm -rf $(BUILD_DIR)

.PHONY: all clean
