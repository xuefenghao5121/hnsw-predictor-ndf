CXX = g++
CXXFLAGS = -O3 -std=c++17 -Wall -Wextra -I../../hnswlib -I../../include -I. -march=native
LDFLAGS = -pthread

BUILD_DIR = build

CORE_SRC = disk_hnsw_iouring.cpp block_cache.cpp ../../src/core/graph_prefetcher.cpp
HEADERS = disk_hnsw_iouring.h ../../include/block_cache.h ../../include/common.h \
          ../../include/layout_provider.h ../../include/replacement_policy.h \
          ../../include/graph_prefetcher.h ../../include/io_uring_wrapper.h

all: $(BUILD_DIR)/benchmark_iouring

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/benchmark_iouring: benchmark_iouring.cpp $(CORE_SRC) $(HEADERS) | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ benchmark_iouring.cpp $(CORE_SRC) $(LDFLAGS)

clean:
	rm -f $(BUILD_DIR)/*

.PHONY: all clean
