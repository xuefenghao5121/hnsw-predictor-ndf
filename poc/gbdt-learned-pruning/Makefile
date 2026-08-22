# poc/gbdt-learned-pruning/Makefile - POC 编译

CXX ?= g++
CXXFLAGS ?= -O3 -mavx2 -std=c++17 -DNDEBUG -I../../include -I../../hnswlib -I.
LDFLAGS ?= -lpthread

SRC = disk_hnsw_llsp.cpp ../../src/core/block_cache.cpp ../../src/core/graph_prefetcher.cpp
HDR = $(wildcard ../../include/*.h)

BIN = benchmark_llsp

all: $(BIN)

$(BIN): benchmark_llsp.cpp $(SRC) $(HDR)
	$(CXX) $(CXXFLAGS) -o $@ benchmark_llsp.cpp $(SRC) $(LDFLAGS)

clean:
	rm -f $(BIN)

.PHONY: all clean
