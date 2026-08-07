# Makefile - csr-on-disk POC

CXX ?= g++
CXXFLAGS ?= -O3 -mavx2 -std=c++17 -DNDEBUG -I../../include -I../../hnswlib -I.
LDFLAGS ?= -lpthread

# Extract tool
EXTRACT = extract_csr
EXTRACT_SRC = extract_csr.cpp

# POC benchmark (patched disk_hnsw + benchmark using mmap CSR)
POC_BIN = benchmark_csr_disk
POC_SRC = disk_hnsw_csr.cpp ../../src/core/block_cache.cpp ../../src/core/graph_prefetcher.cpp
POC_HDR = $(wildcard ../../include/*.h)

all: $(EXTRACT) $(POC_BIN)

$(EXTRACT): $(EXTRACT_SRC)
	$(CXX) $(CXXFLAGS) -o $@ $<

$(POC_BIN): benchmark_csr_disk.cpp $(POC_SRC) $(POC_HDR)
	$(CXX) $(CXXFLAGS) -o $@ benchmark_csr_disk.cpp $(POC_SRC) $(LDFLAGS)

clean:
	rm -f $(EXTRACT) $(POC_BIN)

.PHONY: all clean
