#!/bin/bash
# run_sift1m_scaling.sh - SIFT1M full scaling sweep with CON-SLA-014
set -euo pipefail

PROJ_ROOT="/home/huawei/hnsw-predictor-ndf"
POC_DIR="$PROJ_ROOT/poc/multi-thread-scaling"
BIN="$POC_DIR/build"
CGROUP_PATH="/sys/fs/cgroup/hnsw_scaling"
RESULTS="$POC_DIR/results_sift1m.txt"
SUDO="echo huawei | sudo -S"

echo "" > "$RESULTS"
echo "=== SIFT1M Scaling Sweep (CON-SLA-014, 512MB cgroup) ===" >> "$RESULTS"

# Setup cgroup and join it ONCE for the whole script
echo "huawei" | sudo -S bash -c "mkdir -p $CGROUP_PATH && echo \$((512 * 1024 * 1024)) > $CGROUP_PATH/memory.max && echo $$ > $CGROUP_PATH/cgroup.procs" 2>/dev/null

# Verify we're in the cgroup
CGROUP_CHECK=$(cat /proc/self/cgroup 2>/dev/null | grep hnsw_scaling || echo "NOT IN CGROUP")
echo "Cgroup check: $CGROUP_CHECK"

drop_caches() {
    echo "huawei" | sudo -S bash -c 'sync && echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null
}

collect_cgroup_stats() {
    echo "  cgroup_peak: $(cat $CGROUP_PATH/memory.peak 2>/dev/null || echo N/A)"
    echo "  cgroup_oom: $(grep oom $CGROUP_PATH/memory.events 2>/dev/null || echo N/A)"
    echo "  cgroup_anon: $(grep '^anon' $CGROUP_PATH/memory.stat 2>/dev/null || echo N/A)"
    echo "  cgroup_file: $(grep '^file' $CGROUP_PATH/memory.stat 2>/dev/null || echo N/A)"
}

# ---- DiskHNSW scaling ----
echo "=== DiskHNSW Scaling ===" >> "$RESULTS"
for T in 1 2 4 8 12 16 24; do
    echo ""
    echo "=== DiskHNSW ${T}T ==="
    drop_caches
    # Reset cgroup stats by re-creating
    echo "huawei" | sudo -S bash -c "echo 0 > $CGROUP_PATH/memory.peak 2>/dev/null; true" 2>/dev/null

    OUTPUT=$(TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1 \
        L4_EVICT_META=1 L4_WILLNEED=1 \
        VEC_BLOCKS_PATH=$PROJ_ROOT/output/sift1m_vecblocks_64k.bin \
        PQ_CODES_PATH=$PROJ_ROOT/output/pqco_sift1m_M32_correct.bin \
        CACHE_MB=64 FLAT_VEC_MB=64 REFINE_EF=100 \
        NUM_THREADS=$T \
        "$BIN/benchmark_diskhnsw_mt" \
        $PROJ_ROOT/output/sift1m_graph.bin $PROJ_ROOT/output/sift1m_bfs.bin \
        $PROJ_ROOT/output/sift1m_blocks_64k.bin $PROJ_ROOT/output/sift1m_route_64k.bin \
        $PROJ_ROOT/data/sift_base.fvecs $PROJ_ROOT/data/sift1m_query200.fvecs $PROJ_ROOT/data/sift1m_gt200.bin \
        10 100 200 2>&1)

    echo "$OUTPUT" | grep -E "Recall:|Mean:|P50:|P95:|P99:|QPS:|RSS:" | while read line; do
        echo "  $line"
    done
    STATS=$(collect_cgroup_stats)
    echo "$STATS"

    echo "--- ${T}T ---" >> "$RESULTS"
    echo "$OUTPUT" | grep -E "Recall:|Mean:|P50:|P95:|P99:|QPS:|RSS:" >> "$RESULTS"
    echo "$STATS" >> "$RESULTS"
done

# ---- hnswlib native scaling ----
echo ""
echo "=== hnswlib Native Scaling ==="
echo "" >> "$RESULTS"
echo "=== hnswlib Native Scaling ===" >> "$RESULTS"
for T in 1 2 4 8 12 16 24; do
    echo ""
    echo "=== hnswlib native ${T}T ==="
    drop_caches

    OUTPUT=$(NUM_THREADS=$T \
        "$BIN/benchmark_hnswlib_native_mt" \
        $PROJ_ROOT/output/sift1m_index.bin \
        $PROJ_ROOT/data/sift1m_query200.fvecs $PROJ_ROOT/data/sift1m_gt200.bin \
        10 100 200 2>&1)

    echo "$OUTPUT" | grep -E "Recall:|Mean:|P50:|P95:|P99:|QPS:|RSS:" | while read line; do
        echo "  $line"
    done
    STATS=$(collect_cgroup_stats)
    echo "$STATS"

    echo "--- ${T}T ---" >> "$RESULTS"
    echo "$OUTPUT" | grep -E "Recall:|Mean:|P50:|P95:|P99:|QPS:|RSS:" >> "$RESULTS"
    echo "$STATS" >> "$RESULTS"
done

echo ""
echo "=== SIFT1M scaling sweep complete. Results: $RESULTS ==="
cat "$RESULTS"
