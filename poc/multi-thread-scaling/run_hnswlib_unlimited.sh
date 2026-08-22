#!/bin/bash
# run_hnswlib_unlimited.sh - hnswlib native scaling WITHOUT cgroup (no memory limit)
# Purpose: fair comparison - hnswlib with enough memory
# Protocol: drop_caches only (no cgroup), same thread sweep
set -euo pipefail

PROJ_ROOT="/home/huawei/hnsw-predictor-ndf"
POC_DIR="$PROJ_ROOT/poc/multi-thread-scaling"
BIN="$POC_DIR/build"
RESULTS="$POC_DIR/results_hnswlib_unlimited.txt"

echo "" > "$RESULTS"
echo "=== hnswlib Native Scaling (NO cgroup, drop_caches only) ===" >> "$RESULTS"

# Leave any existing cgroup
echo "huawei" | sudo -S bash -c 'echo 1 > /sys/fs/cgroup/hnsw_scaling/memory.max' 2>/dev/null || true

drop_caches() {
    echo "huawei" | sudo -S bash -c 'sync && echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null
}

# ---- hnswlib native SIFT1M (unlimited memory) ----
echo "=== hnswlib Native SIFT1M (unlimited memory) ===" >> "$RESULTS"
for T in 1 2 4 8 12 16 24; do
    echo ""
    echo "=== hnswlib native SIFT1M ${T}T (unlimited) ==="
    drop_caches

    OUTPUT=$(NUM_THREADS=$T \
        "$BIN/benchmark_hnswlib_native_mt" \
        $PROJ_ROOT/output/sift1m_index.bin \
        $PROJ_ROOT/data/sift1m_query200.fvecs $PROJ_ROOT/data/sift1m_gt200.bin \
        10 100 200 2>&1)

    echo "$OUTPUT" | grep -E "Recall:|Mean:|P50:|P95:|P99:|QPS:|RSS:" | while read line; do
        echo "  $line"
    done

    echo "--- ${T}T ---" >> "$RESULTS"
    echo "$OUTPUT" | grep -E "Recall:|Mean:|P50:|P95:|P99:|QPS:|RSS:" >> "$RESULTS"
done

# ---- hnswlib native DEEP10M (unlimited memory) ----
echo "" >> "$RESULTS"
echo "=== hnswlib Native DEEP10M (unlimited memory) ===" >> "$RESULTS"
for T in 1 2 4 8 12; do
    echo ""
    echo "=== hnswlib native DEEP10M ${T}T (unlimited) ==="
    drop_caches

    OUTPUT=$(NUM_THREADS=$T \
        "$BIN/benchmark_hnswlib_native_mt" \
        $PROJ_ROOT/output/deep10m_index.bin \
        $PROJ_ROOT/data/deep10m_query.fvecs $PROJ_ROOT/data/deep10m_gt_k10.bin \
        10 300 10000 2>&1)

    echo "$OUTPUT" | grep -E "Recall:|Mean:|P50:|P95:|P99:|QPS:|RSS:" | while read line; do
        echo "  $line"
    done

    echo "--- ${T}T ---" >> "$RESULTS"
    echo "$OUTPUT" | grep -E "Recall:|Mean:|P50:|P95:|P99:|QPS:|RSS:" >> "$RESULTS"
done

echo ""
echo "=== hnswlib unlimited scaling sweep complete ==="
cat "$RESULTS"
