#!/bin/bash
# R0+R1: baseline (WILLNEED_BG+pread) vs io_uring (buffered)
# SIFT1M, 256MB cgroup, 1T
set -euo pipefail
cd /home/huawei/hnsw-predictor-ndf/poc/fine-rerank-iouring
BIN=build/benchmark_iouring

GRAPH=../../output/sift1m_graph.bin
BFS=../../output/sift1m_bfs.bin
BLOCKS=../../output/sift1m_blocks_64k.bin
ROUTE=../../output/sift1m_route_64k.bin
DATA=../../data/sift_base.fvecs
QUERY=../../data/sift1m_query200.fvecs
GT=../../data/sift1m_gt200.bin
K=10; EF=100; NUMQ=200

CGROUP_MB=${1:-256}
CGROUP_PATH=/sys/fs/cgroup/hnsw_iouring

export TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
export VEC_BLOCKS_PATH=../../output/sift1m_vecblocks_64k.bin
export PQ_CODES_PATH=../../output/pqco_sift1m_M32_correct.bin
export REFINE_EF=100 CACHE_MB=64 EVICT_PAGE_CACHE=0 NUM_THREADS=0
export PROFILE_TS=1

# Setup cgroup
sync; echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null
sudo mkdir -p "$CGROUP_PATH"
echo "$((CGROUP_MB * 1024 * 1024))" | sudo tee "$CGROUP_PATH/memory.max" > /dev/null

run_test() {
    local name=$1; shift
    local extra_env=$1; shift
    echo ""
    echo "============================================"
    echo "  $name (cgroup=${CGROUP_MB}MB)"
    echo "============================================"
    sync; echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null
    echo $$ | sudo tee "$CGROUP_PATH/cgroup.procs" > /dev/null
    env $extra_env $BIN $GRAPH $BFS $BLOCKS $ROUTE $DATA $QUERY $GT $K $EF $NUMQ 2>&1 || true
    # cgroup stats
    echo "--- cgroup stats ---"
    grep -E "^(anon|file|workingset_refault_file|pgmajfault)" "$CGROUP_PATH/memory.stat" 2>/dev/null
    echo "peak: $(cat "$CGROUP_PATH/memory.peak" 2>/dev/null)"
    echo "oom: $(grep oom "$CGROUP_PATH/memory.events" 2>/dev/null)"
}

# Determine FVC based on cgroup
if [ "$CGROUP_MB" = "256" ]; then
    FVC=64
    WILLNEED_BG=1
    PAGE_MERGE=1
    VL_POOL=14
else
    FVC=160
    WILLNEED_BG=1
    PAGE_MERGE=0
    VL_POOL=14
fi

# R0: Baseline (WILLNEED_BG + pread)
run_test "R0: WILLNEED_BG + pread (baseline)" \
    "L4_WILLNEED=1 WILLNEED_BG=$WILLNEED_BG PAGE_MERGE_BG=$PAGE_MERGE VL_POOL_THREADS=$VL_POOL FLAT_VEC_MB=$FVC"

# R1: io_uring (buffered)
run_test "R1: per-thread io_uring (buffered)" \
    "FINE_IOURING=1 FLAT_VEC_MB=$FVC VL_POOL_THREADS=$VL_POOL"

# R2: io_uring + fadvise hybrid (串行)
run_test "R2: io_uring + fadvise hybrid (serial)" \
    "FINE_IOURING=1 IOURING_HYBRID=1 FLAT_VEC_MB=$FVC VL_POOL_THREADS=$VL_POOL"

# R3: io_uring + BG fadvise async (并行)
run_test "R3: io_uring + BG fadvise async (parallel)" \
    "FINE_IOURING=1 IOURING_ASYNC=1 FLAT_VEC_MB=$FVC VL_POOL_THREADS=$VL_POOL"

echo ""
echo "============================================"
echo "  R0+R1 complete"
echo "============================================"
