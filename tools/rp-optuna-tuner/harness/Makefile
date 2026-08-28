# tools/rp-optuna-tuner/harness/Makefile — RPT tuner binaries (copy-then-edit of CAT
# harness Makefile, [[BEH-018]] / [[BEH-029]]).
#
# Three tuner-local binaries, all compiled against harness/disk_hnsw_llsp.cpp (a thin
# instrumented copy of Trunk src/core/disk_hnsw.cpp + an inert-unless-PROFILE_LLSP dump
# block). The sustained MEASUREMENT defaults to Trunk build/benchmark_sustained via
# scripts/run_sustained.sh ([[BEH-029]]); benchmark_sustained_poc below exists ONLY for
# the per-artifact GBDT on-leg, whose model header must NOT overwrite Trunk
# include/gbdt_model.h ([[BEH-029]]).
#
#   benchmark_llsp            — profiling runner (PROFILE_LLSP=1 -> [LLSP] dump to stderr)
#   benchmark_sustained_poc   — sustained measurement binary. Its gbdt_model.h resolves
#     from THIS directory (quote-include from disk_hnsw_llsp.cpp), i.e. the RETRAINED
#     harness/gbdt_model.h — MUST NOT test Trunk include/gbdt_model.h ([[BEH-RPT-002]]).
#     Rebuild after retrain overwrites the header.
#
#   tune_main                 — cheap DSE driver (prune → search → validate), self-test.
#   robust_prune_main         — offline RobustPrune(α₂) graph rewrite CLI ([[BEH-RPT-001]]).
#
# Flags mirror the Trunk Makefile (g++ -O3 -std=c++17 -Wall -Wextra -march=native).
CXX ?= g++
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -march=native
INC = -I../../../hnswlib -I../../../include -I../include
LDFLAGS ?= -pthread

REPO = ../../..
CORE_LLSP = disk_hnsw_llsp.cpp
TRUNK_CORE = $(REPO)/src/core/block_cache.cpp $(REPO)/src/core/graph_prefetcher.cpp
SUSTAINED_SRC = $(REPO)/src/benchmark/benchmark_sustained.cpp
BIN = ../harness-bin

all: $(BIN)/benchmark_llsp $(BIN)/benchmark_sustained_poc $(BIN)/tune_main $(BIN)/robust_prune_main

$(BIN):
	mkdir -p $(BIN)

$(BIN)/benchmark_llsp: benchmark_llsp.cpp $(CORE_LLSP) $(TRUNK_CORE) | $(BIN)
	$(CXX) $(CXXFLAGS) $(INC) -o $@ benchmark_llsp.cpp $(CORE_LLSP) $(TRUNK_CORE) $(LDFLAGS)

$(BIN)/benchmark_sustained_poc: $(SUSTAINED_SRC) $(CORE_LLSP) $(TRUNK_CORE) gbdt_model_active.h | $(BIN)
	$(CXX) $(CXXFLAGS) $(INC) -o $@ $(SUSTAINED_SRC) $(CORE_LLSP) $(TRUNK_CORE) $(LDFLAGS)

$(BIN)/tune_main: tune_main.cpp ../include/rpt_types.h ../pruner/pruner.h ../searcher/searcher.h | $(BIN)
	$(CXX) -O2 -std=c++17 -I.. -o $@ tune_main.cpp $(LDFLAGS)

$(BIN)/robust_prune_main: ../rp/robust_prune_main.cpp ../rp/robust_prune.h | $(BIN)
	$(CXX) $(CXXFLAGS) -I../../../include -o $@ ../rp/robust_prune_main.cpp $(LDFLAGS)

clean:
	rm -f $(BIN)/benchmark_llsp $(BIN)/benchmark_sustained_poc $(BIN)/tune_main $(BIN)/robust_prune_main

.PHONY: all clean
