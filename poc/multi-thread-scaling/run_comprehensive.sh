#!/bin/bash
# Comprehensive sweep: DiskHNSW (512MB+256MB) vs hnswlib (unlimited)
set -euo pipefail

PROJ="/home/huawei/hnsw-predictor-ndf"
BIN_DHN="$PROJ/poc/multi-thread-scaling/build/benchmark_diskhnsw_mt"
BIN_HNSW="$PROJ/poc/multi-thread-scaling/build/benchmark_hnswlib_native_mt"
CGROUP="/sys/fs/cgroup/hnsw_test"
RESULTS="$PROJ/poc/multi-thread-scaling/results_comprehensive.txt"
THREADS="1 2 4 6 8 10 12 14 16 18 20 22 24"

echo "=== Comprehensive Scaling Sweep (2026-08-05) ===" > "$RESULTS"
echo "Protocol: CON-SLA-014, drop_caches + cgroup" >> "$RESULTS"
echo "DiskHNSW: WILLNEED_BG=1 VL_POOL_THREADS=14" >> "$RESULTS"
echo "" >> "$RESULTS"

run_diskhnsw() {
    local CGROUP_MB=$1 FVC=$2 T=$3 EXTRA=$4
    echo "huawei" | sudo -S bash -c "
        rmdir $CGROUP 2>/dev/null; mkdir -p $CGROUP
        echo \$(( ${CGROUP_MB} * 1024 * 1024 )) > $CGROUP/memory.max
        sync && echo 3 > /proc/sys/vm/drop_caches
        echo \$\$ > $CGROUP/cgroup.procs
        cd $PROJ
        TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1 \
        L4_EVICT_META=1 L4_WILLNEED=1 \
        VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin \
        PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin \
        CACHE_MB=64 FLAT_VEC_MB=$FVC REFINE_EF=100 \
        NUM_THREADS=$T $EXTRA \
        $BIN_DHN output/sift1m_graph.bin output/sift1m_bfs.bin \
        output/sift1m_blocks_64k.bin output/sift1m_route_64k.bin \
        data/sift_base.fvecs data/sift1m_query200.fvecs data/sift1m_gt200.bin \
        10 100 200 2>&1
        echo \"oom: \$(grep 'oom ' $CGROUP/memory.events)\"
    " 2>&1
}

run_hnswlib() {
    local T=$1
    echo "huawei" | sudo -S bash -c "
        rmdir $CGROUP 2>/dev/null
        sync && echo 3 > /proc/sys/vm/drop_caches
        cd $PROJ
        NUM_THREADS=$T \
        $BIN_HNSW output/sift1m_index.bin \
        data/sift1m_query200.fvecs data/sift1m_gt200.bin \
        10 100 200 2>&1
    " 2>&1
}

echo "=== hnswlib unlimited ===" | tee -a "$RESULTS"
for T in $THREADS; do
    echo "hnswlib ${T}T..." >&2
    OUT=$(run_hnswlib $T)
    QPS=$(echo "$OUT" | grep "QPS:" | awk '{print $2}')
    REC=$(echo "$OUT" | grep "Recall:" | awk '{print $2}')
    echo "${T}T $QPS $REC" | tee -a "$RESULTS"
done

echo "" | tee -a "$RESULTS"
echo "=== DiskHNSW 512MB (FVC=160, BG=1, VL_POOL@14) ===" | tee -a "$RESULTS"
for T in $THREADS; do
    echo "dhnsw 512MB ${T}T..." >&2
    OUT=$(run_diskhnsw 512 160 $T "WILLNEED_BG=1 VL_POOL_THREADS=14")
    QPS=$(echo "$OUT" | grep "QPS:" | awk '{print $2}')
    REC=$(echo "$OUT" | grep "Recall:" | awk '{print $2}')
    OOM=$(echo "$OUT" | grep "oom:" | awk '{print $2}')
    echo "${T}T $QPS $REC oom=$OOM" | tee -a "$RESULTS"
done

echo "" | tee -a "$RESULTS"
echo "=== DiskHNSW 256MB (FVC=64, BG=1, VL_POOL@14) ===" | tee -a "$RESULTS"
for T in $THREADS; do
    echo "dhnsw 256MB ${T}T..." >&2
    OUT=$(run_diskhnsw 256 64 $T "WILLNEED_BG=1 VL_POOL_THREADS=14")
    QPS=$(echo "$OUT" | grep "QPS:" | awk '{print $2}')
    REC=$(echo "$OUT" | grep "Recall:" | awk '{print $2}')
    OOM=$(echo "$OUT" | grep "oom:" | awk '{print $2}')
    echo "${T}T $QPS $REC oom=$OOM" | tee -a "$RESULTS"
done

echo "" | tee -a "$RESULTS"
echo "=== Done ===" | tee -a "$RESULTS"
