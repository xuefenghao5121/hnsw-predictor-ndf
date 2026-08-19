# hotspot-optimization — R0 contrast workspace (poc_prepare_baseline)
#
# Byte-identical copies of Trunk search core + SIMD headers.
# This hop does NOT edit pqDistance (D1 SIMD gather is a later implement hop).
# Read-only link: Trunk block_cache / graph_prefetcher / benchmark_sustained.
#
# Contrast sources (from repo root, pinned baseline_trunk_sha
# a14339234133cc6c5a2348464954f744c6465efb; identical on current HEAD):
#   src/core/disk_hnsw.cpp          → src/disk_hnsw.cpp
#   include/disk_hnsw.h             → src/disk_hnsw.h
#   include/simd.h                  → src/simd.h
#   include/simd_x86.h              → src/simd_x86.h
#   include/simd_arm.h              → src/simd_arm.h
#   include/simd_scalar.h           → src/simd_scalar.h
#
# Measure (later poc_measurement): BIN=poc/hotspot-optimization/build/benchmark_sustained \
#   bash scripts/run_sustained.sh --config cfg-m24-ef60

CXX = g++
# -Isrc first so the topic copies of disk_hnsw.h / simd*.h win over Trunk include/.
CXXFLAGS = -O3 -std=c++17 -Wall -Wextra -Isrc -I../../include -I../../hnswlib -I../.. -march=native
LDFLAGS = -pthread

BUILD_DIR = build
TOPIC_CORE = src/disk_hnsw.cpp
TRUNK_CORE = ../../src/core/block_cache.cpp ../../src/core/graph_prefetcher.cpp
BENCH_SRC = ../../src/benchmark/benchmark_sustained.cpp
HEADERS = src/disk_hnsw.h src/simd.h src/simd_x86.h src/simd_arm.h src/simd_scalar.h \
          $(wildcard ../../include/*.h)

$(BUILD_DIR)/benchmark_sustained: $(BENCH_SRC) $(TOPIC_CORE) $(TRUNK_CORE) $(HEADERS) | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ $(BENCH_SRC) $(TOPIC_CORE) $(TRUNK_CORE) $(LDFLAGS)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

all: $(BUILD_DIR)/benchmark_sustained

clean:
	rm -f $(BUILD_DIR)/benchmark_sustained

.PHONY: all clean
