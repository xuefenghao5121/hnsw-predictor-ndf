#!/bin/bash
# run_fvc_sweep.sh - flat_vec_cache tuning sweep (Direction 1)
# Protocol: CON-SLA-014, SIFT1M 512MB cgroup, 4T
set -euo pipefail

PROJ_ROOT="/home/huawei/hnsw-predictor-ndf"
BIN="$PROJ_ROOT/build/benchmark_diskhnsw"
CGROUP_PATH="/sys/fs/cgroup/hnsw_test"
RESULTS="$PROJ_ROOT/poc/perf-gap-4t/results_fvc_sweep.txt"

echo "=== flat_vec_cache Sweep (SIFT1M 4T, 512MB cgroup, CON-SLA-014) ===" > "$RESULTS"
echo "Baseline: FLAT_VEC_MB=64 -> 9657 QPS / 95.80% recall" >> "$RESULTS"
echo "" >> "$RESULTS"

# Setup cgroup
echo "huawei" | sudo -S bash -c "mkdir -p $CGROUP_PATH && echo \$((512 * 1024 * 1024)) > $CGROUP_PATH/memory.max" 2>/dev/null
echo $$ | sudo tee "$CGROUP_PATH/cgroup.procs" > /dev/null
cat /proc/self/cgroup | grep hnsw_test && echo "In cgroup" || echo "NOT in cgroup!"

drop_caches() {
    echo "huawei" | sudo -S bash -c 'sync && echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null
}

for FVC in 64 96 128 160 192; do
    echo ""
    echo "=== FLAT_VEC_MB=$FVC ==="
    drop_caches

    OUTPUT=$(TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1 \
        L4_EVICT_META=1 L4_WILLNEED=1 \
        VEC_BLOCKS_PATH=$PROJ_ROOT/output/sift1m_vecblocks_64k.bin \
        PQ_CODES_PATH=$PROJ_ROOT/output/pqco_sift1m_M32_correct.bin \
        CACHE_MB=64 FLAT_VEC_MB=$FVC REFINE_EF=100 \
        NUM_THREADS=4 \
        "$BIN" \
        $PROJ_ROOT/output/sift1m_graph.bin $PROJ_ROOT/output/sift1m_bfs.bin \
        $PROJ_ROOT/output/sift1m_blocks_64k.bin $PROJ_ROOT/output/sift1m_route_64k.bin \
        $PROJ_ROOT/data/sift_base.fvecs $PROJ_ROOT/data/sift1m_query200.fvecs $PROJ_ROOT/data/sift1m_gt200.bin \
        10 100 200 2>&1)

    echo "$OUTPUT" | grep -E "Recall:|Mean:|P50:|P95:|P99:|QPS:|RSS:" | while read line; do
        echo "  $line"
    done

    # cgroup stats
    PEAK=$(cat $CGROUP_PATH/memory.peak 2>/dev/null || echo N/A)
    OOM=$(grep "oom " $CGROUP_PATH/memory.events 2>/dev/null | head -1 || echo N/A)
    ANON=$(grep '^anon ' $CGROUP_PATH/memory.stat 2>/dev/null || echo N/A)
    FILE=$(grep '^file ' $CGROUP_PATH/memory.stat 2>/dev/null || echo N/A)
    echo "  cgroup_peak: $PEAK  oom: $OOM  anon: $ANON  file: $FILE"

    echo "--- FLAT_VEC_MB=$FVC ---" >> "$RESULTS"
    echo "$OUTPUT" | grep -E "Recall:|Mean:|P50:|P95:|P99:|QPS:|RSS:" >> "$RESULTS"
    echo "  cgroup_peak: $PEAK  oom: $OOM  anon: $ANON  file: $FILE" >> "$RESULTS"
    echo "" >> "$RESULTS"
done

echo ""
echo "=== Sweep complete ==="
cat "$RESULTS"
