# POC Makefile: ssd-parallelism-io
REPO := $(shell cd ../.. && pwd)
CXX := g++
CXXFLAGS := -O3 -std=c++17 -Wall -Wextra -I$(REPO)/hnswlib -I$(REPO)/include -I. -march=native
LDFLAGS := -pthread -luring

BUILD_DIR := build
BIN := $(BUILD_DIR)/benchmark_cqe

SRCS := disk_hnsw.cpp graph_prefetcher.cpp block_cache.cpp benchmark_cqe.cpp

all: $(BIN)

$(BIN): $(SRCS) | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ $(SRCS) $(LDFLAGS)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

clean:
	rm -rf $(BUILD_DIR)
