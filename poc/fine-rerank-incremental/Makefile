# poc/fine-rerank-incremental/Makefile
#
# Topic: fine-rerank-incremental
# Clauses: CON-SLA-020 (reference)
#
# This POC patches Phase B of disk_hnsw to implement incremental pread + batch early stop.
# It compiles the patched disk_hnsw_poc.cpp/h with the UNMODIFIED benchmark harness.

CXX ?= g++
CXXFLAGS ?= -O3 -mavx2 -std=c++17 -DNDEBUG -I../../include -I../../hnswlib -I.
LDFLAGS ?= -lpthread

# POC patched sources
POC_SRC = disk_hnsw_poc.cpp
POC_HDR = disk_hnsw_poc.h

# Unmodified Trunk sources (linked as-is)
TRUNK_SRC = ../../src/core/block_cache.cpp \
            ../../src/core/graph_prefetcher.cpp

HDR = $(POC_HDR) $(wildcard ../../include/*.h)

BIN = benchmark_sustained_inc

all: $(BIN)

$(BIN): benchmark_sustained.cpp $(POC_SRC) $(TRUNK_SRC) $(HDR)
	$(CXX) $(CXXFLAGS) -o $@ benchmark_sustained.cpp $(POC_SRC) $(TRUNK_SRC) $(LDFLAGS)

clean:
	rm -f $(BIN)

.PHONY: all clean
