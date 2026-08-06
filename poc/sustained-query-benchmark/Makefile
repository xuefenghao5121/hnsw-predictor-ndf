# poc/sustained-query-benchmark/Makefile
#
# Topic: sustained-query-benchmark
# Clauses: BEH-035, API-019
#
# NOTE: This POC changes measurement methodology only — it links the UNMODIFIED
# Trunk engine sources. There is no patched copy of disk_hnsw.cpp, because the
# hypothesis under test is about the benchmark harness, not the search engine.

CXX ?= g++
CXXFLAGS ?= -O3 -mavx2 -std=c++17 -DNDEBUG -I../../include -I../../hnswlib -I.
LDFLAGS ?= -lpthread

TRUNK_SRC = ../../src/core/disk_hnsw.cpp \
            ../../src/core/block_cache.cpp \
            ../../src/core/graph_prefetcher.cpp

HDR = $(wildcard ../../include/*.h)

BIN = benchmark_sustained

all: $(BIN)

$(BIN): benchmark_sustained.cpp $(TRUNK_SRC) $(HDR)
	$(CXX) $(CXXFLAGS) -o $@ benchmark_sustained.cpp $(TRUNK_SRC) $(LDFLAGS)

clean:
	rm -f $(BIN)

.PHONY: all clean
