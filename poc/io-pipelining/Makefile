# poc/io-pipelining/Makefile - I/O Pipelining POC 构建
# 独立于主 Makefile, 从 poc/ 目录编译 patched copy, 不污染 src/

CXX = g++
CXXFLAGS = -O3 -std=c++17 -Wall -Wextra -I./hnswlib -I./include -I./poc/io-pipelining -march=native
LDFLAGS = -pthread

BUILD_DIR = build
POC_DIR = poc/io-pipelining

POC_HDR = $(POC_DIR)/disk_hnsw_pipe.h
POC_SRC = $(POC_DIR)/disk_hnsw_pipe.cpp
POC_BENCH = $(POC_DIR)/benchmark_pipe.cpp
CORE_SRC = src/core/block_cache.cpp src/core/graph_prefetcher.cpp

# POC benchmark: patched benchmark + patched disk_hnsw + 原 block_cache/graph_prefetcher
$(BUILD_DIR)/benchmark_pipe: $(POC_BENCH) $(POC_SRC) $(CORE_SRC) $(POC_HDR) | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ $(POC_BENCH) $(POC_SRC) $(CORE_SRC) $(LDFLAGS)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

clean:
	rm -f $(BUILD_DIR)/benchmark_pipe

.PHONY: clean
