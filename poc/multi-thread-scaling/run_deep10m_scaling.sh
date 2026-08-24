#!/bin/bash
# run_deep10m_scaling.sh - DEEP10M scaling sweep with CON-SLA-014
set -euo pipefail

PROJ_ROOT="/home/huawei/hnsw-predictor-ndf"
POC_DIR="$PROJ_ROOT/poc/multi-thread-scaling"
BIN="$POC_DIR/build"
CGROUP_PATH="/sys/fs/cgroup/hnsw_scaling"
RESULTS="$POC_DIR/results_deep10m.txt"

echo "" > "$RESULTS"
echo "=== DEEP10M Scaling Sweep (CON-SLA-014, 2GB cgroup) ===" >> "$RESULTS"

# Setup cgroup (2GB for DEEP10M) and join
# Note: $$ must NOT be escaped - it needs to be the parent shell's PID
echo "huawei" | sudo -S bash -c "mkdir -p $CGROUP_PATH && echo \$((2048 * 1024 * 1024)) > $CGROUP_PATH/memory.max" 2>/dev/null
echo $$ | sudo tee "$CGROUP_PATH/cgroup.procs" > /dev/null

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

# ---- DiskHNSW DEEP10M scaling ----
echo "=== DiskHNSW DEEP10M Scaling ===" >> "$RESULTS"
for T in 1 2 4 8 12; do
    echo ""
    echo "=== DiskHNSW DEEP10M ${T}T ==="
    drop_caches

    OUTPUT=$(TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1 \
        L4_EVICT_META=1 L4_WILLNEED=1 \
        VEC_BLOCKS_PATH=$PROJ_ROOT/output/deep10m_vecblocks_64k.bin \
        PQ_CODES_PATH=$PROJ_ROOT/output/pqco_deep10m_M32.bin \
        CACHE_MB=64 FLAT_VEC_MB=64 REFINE_EF=300 \
        NUM_THREADS=$T \
        "$BIN/benchmark_diskhnsw_mt" \
        $PROJ_ROOT/output/deep10m_graph.bin $PROJ_ROOT/output/deep10m_bfs.bin \
        $PROJ_ROOT/output/deep10m_blocks_64k.bin $PROJ_ROOT/output/deep10m_route_64k.bin \
        $PROJ_ROOT/data/deep10m_base.fvecs $PROJ_ROOT/data/deep10m_query.fvecs $PROJ_ROOT/data/deep10m_gt_k10.bin \
        10 300 10000 2>&1)

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
echo "=== DEEP10M scaling sweep complete ==="
cat "$RESULTS"
