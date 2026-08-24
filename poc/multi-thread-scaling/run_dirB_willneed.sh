#!/bin/bash
# Direction B: WILLNEED adaptive disable sweep
set -euo pipefail

PROJ="/home/huawei/hnsw-predictor-ndf"
BIN="$PROJ/poc/multi-thread-scaling/build/benchmark_diskhnsw_mt"
CGROUP="/sys/fs/cgroup/hnsw_test"

run_test() {
    local CGROUP_MB=$1
    local FVC=$2
    local T=$3
    local EXTRA_ENV=$4
    local LABEL=$5

    echo "huawei" | sudo -S bash -c "
        rmdir $CGROUP 2>/dev/null
        mkdir -p $CGROUP
        echo \$(( ${CGROUP_MB} * 1024 * 1024 )) > $CGROUP/memory.max
        sync && echo 3 > /proc/sys/vm/drop_caches
        echo \$\$ > $CGROUP/cgroup.procs
        cd $PROJ
        TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1 \
        L4_EVICT_META=1 L4_WILLNEED=1 \
        VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin \
        PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin \
        CACHE_MB=64 FLAT_VEC_MB=$FVC REFINE_EF=100 \
        NUM_THREADS=$T $EXTRA_ENV \
        $BIN \
            output/sift1m_graph.bin output/sift1m_bfs.bin \
            output/sift1m_blocks_64k.bin output/sift1m_route_64k.bin \
            data/sift_base.fvecs data/sift1m_query200.fvecs data/sift1m_gt200.bin \
            10 100 200 2>&1
        echo \"oom: \$(grep 'oom ' $CGROUP/memory.events)\"
    " 2>&1 | grep -E "Recall:|QPS:|Mean:|P99:|oom:" | while read line; do
        echo "  [$LABEL] $line"
    done
}

echo "=========================================="
echo "=== Direction B: WILLNEED Adaptive Disable ==="
echo "=========================================="

for T in 8 12 16 24; do
    echo ""
    echo "=== ${T}T ==="
    echo "-- 512MB (FVC=160) --"
    run_test 512 160 $T "" "512MB WILLNEED=on"
    run_test 512 160 $T "WILLNEED_DISABLE_THREADS=8" "512MB WILLNEED off@T>=8"

    echo "-- 256MB (FVC=64) --"
    run_test 256 64 $T "" "256MB WILLNEED=on"
    run_test 256 64 $T "WILLNEED_DISABLE_THREADS=8" "256MB WILLNEED off@T>=8"
done

# Control: 1T and 4T should be unaffected (below threshold)
echo ""
echo "=== Control (should be identical) ==="
echo "-- 4T 512MB --"
run_test 512 160 4 "" "512MB WILLNEED=on"
run_test 512 160 4 "WILLNEED_DISABLE_THREADS=8" "512MB WILLNEED off@T>=8 (control)"
