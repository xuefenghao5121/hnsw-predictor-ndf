#!/bin/bash
# run_scaling.sh - Multi-thread scaling sweep
# Protocol: CON-SLA-014 (drop_caches + cgroup)
# Usage: bash run_scaling.sh [sift1m|deep10m]

set -euo pipefail

DATASET="${1:-sift1m}"
PROJ_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
POC_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$POC_DIR/build"

# Dataset configs
if [ "$DATASET" = "sift1m" ]; then
    CGROUP_MB=512
    GRAPH="$PROJ_ROOT/output/sift1m_graph.bin"
    BFS="$PROJ_ROOT/output/sift1m_bfs.bin"
    BLOCKS="$PROJ_ROOT/output/sift1m_blocks_64k.bin"
    ROUTE="$PROJ_ROOT/output/sift1m_route_64k.bin"
    DATA="$PROJ_ROOT/data/sift_base.fvecs"
    QUERY="$PROJ_ROOT/data/sift1m_query200.fvecs"
    GT="$PROJ_ROOT/data/sift1m_gt200.bin"
    VECBLOCKS="$PROJ_ROOT/output/sift1m_vecblocks_64k.bin"
    PQ="$PROJ_ROOT/output/pqco_sift1m_M32_correct.bin"
    DIM=128
    K=10
    EF=100
    REFINE_EF=100
    NUM_Q=200
    THREADS="1 2 4 8 12 16 24"
    HNSWLIB_INDEX="$PROJ_ROOT/output/sift1m_index.bin"
elif [ "$DATASET" = "deep10m" ]; then
    CGROUP_MB=2048
    GRAPH="$PROJ_ROOT/output/deep10m_graph.bin"
    BFS="$PROJ_ROOT/output/deep10m_bfs.bin"
    BLOCKS="$PROJ_ROOT/output/deep10m_blocks_64k.bin"
    ROUTE="$PROJ_ROOT/output/deep10m_route_64k.bin"
    DATA="$PROJ_ROOT/data/deep10m_base.fvecs"
    QUERY="$PROJ_ROOT/data/deep10m_query.fvecs"
    GT="$PROJ_ROOT/data/deep10m_gt_k10.bin"
    VECBLOCKS="$PROJ_ROOT/output/deep10m_vecblocks_64k.bin"
    PQ="$PROJ_ROOT/output/pqco_deep10m_M32.bin"
    DIM=96
    K=10
    EF=300
    REFINE_EF=300
    NUM_Q=10000
    THREADS="1 2 4 8 12"
    HNSWLIB_INDEX="$PROJ_ROOT/output/deep10m_index.bin"
else
    echo "Unknown dataset: $DATASET (use sift1m or deep10m)"
    exit 1
fi

CGROUP_PATH="/sys/fs/cgroup/hnsw_scaling"
CACHE_MB=64
FLAT_VEC_MB=64

echo "=== Multi-thread Scaling Sweep ==="
echo "Dataset: $DATASET | Cgroup: ${CGROUP_MB}MB | Protocol: CON-SLA-014"
echo "Threads: $THREADS"
echo ""

setup_cgroup() {
    echo "Setting up cgroup (${CGROUP_MB}MB)..."
    sudo mkdir -p "$CGROUP_PATH" 2>/dev/null || true
    echo $((CGROUP_MB * 1024 * 1024)) | sudo tee "$CGROUP_PATH/memory.max" > /dev/null
    echo $$ | sudo tee "$CGROUP_PATH/cgroup.procs" > /dev/null
}

drop_caches() {
    sync
    echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null
}

collect_cgroup_stats() {
    echo "--- cgroup stats ---"
    echo "peak: $(cat $CGROUP_PATH/memory.peak 2>/dev/null || echo N/A)"
    echo "oom:  $(grep oom $CGROUP_PATH/memory.events 2>/dev/null || echo N/A)"
    grep -E "^(anon|file)" "$CGROUP_PATH/memory.stat" 2>/dev/null | head -4
}

# ---- DiskHNSW scaling ----
echo "=========================================="
echo "DiskHNSW Scaling"
echo "=========================================="

for T in $THREADS; do
    echo ""
    echo "--- DiskHNSW ${T}T ---"
    drop_caches
    setup_cgroup

    env TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1 \
        L4_EVICT_META=1 L4_WILLNEED=1 \
        VEC_BLOCKS_PATH="$VECBLOCKS" \
        PQ_CODES_PATH="$PQ" \
        CACHE_MB=$CACHE_MB FLAT_VEC_MB=$FLAT_VEC_MB \
        REFINE_EF=$REFINE_EF \
        NUM_THREADS=$T \
        "$BIN/benchmark_diskhnsw_mt" \
        "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" \
        "$DATA" "$QUERY" "$GT" \
        $K $EF $NUM_Q

    collect_cgroup_stats
done

# ---- hnswlib native scaling ----
echo ""
echo "=========================================="
echo "hnswlib Native Scaling"
echo "=========================================="

for T in $THREADS; do
    echo ""
    echo "--- hnswlib native ${T}T ---"
    drop_caches
    setup_cgroup

    env NUM_THREADS=$T \
        "$BIN/benchmark_hnswlib_native_mt" \
        "$HNSWLIB_INDEX" "$QUERY" "$GT" \
        $K $EF $NUM_Q

    collect_cgroup_stats
done

echo ""
echo "=== Scaling sweep complete ==="
