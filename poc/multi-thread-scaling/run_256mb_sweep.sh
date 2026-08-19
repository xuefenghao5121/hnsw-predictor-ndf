#!/bin/bash
# SIFT1M 256MB cgroup scaling sweep (CON-SLA-014 strict)
set -euo pipefail

PROJ="/home/huawei/hnsw-predictor-ndf"
BIN="$PROJ/build/benchmark_diskhnsw"
CGROUP="/sys/fs/cgroup/hnsw_test"
RESULTS="$PROJ/poc/multi-thread-scaling/results_256mb_sweep.txt"

echo "=== SIFT1M 256MB cgroup Scaling Sweep (CON-SLA-014) ===" > "$RESULTS"
echo "Config: WILLNEED=1, FLAT_VEC_MB=64, REFINE_EF=100, FINE_PREAD=1" >> "$RESULTS"
echo "" >> "$RESULTS"

for T in 1 2 4 8 12 16 24; do
    echo ""
    echo "=== ${T}T ==="

    echo "huawei" | sudo -S bash -c "
        rmdir $CGROUP 2>/dev/null
        mkdir -p $CGROUP
        echo \$((256 * 1024 * 1024)) > $CGROUP/memory.max
        sync && echo 3 > /proc/sys/vm/drop_caches
        echo \$\$ > $CGROUP/cgroup.procs
        cd $PROJ
        TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1 \
        L4_EVICT_META=1 L4_WILLNEED=1 \
        VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin \
        PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin \
        CACHE_MB=64 FLAT_VEC_MB=64 REFINE_EF=100 \
        NUM_THREADS=$T \
        $BIN \
            output/sift1m_graph.bin output/sift1m_bfs.bin \
            output/sift1m_blocks_64k.bin output/sift1m_route_64k.bin \
            data/sift_base.fvecs data/sift1m_query200.fvecs data/sift1m_gt200.bin \
            10 100 200 2>&1
        echo \"peak: \$(cat $CGROUP/memory.peak)\"
        echo \"oom: \$(grep 'oom ' $CGROUP/memory.events)\"
        echo \"anon: \$(grep '^anon ' $CGROUP/memory.stat)\"
        echo \"file: \$(grep '^file ' $CGROUP/memory.stat)\"
    " 2>&1 | grep -E "Recall:|QPS:|RSS:|Mean:|P50:|P95:|P99:|Mode:|peak:|oom:|anon:|file:" | tee -a "$RESULTS"

    echo "--- ${T}T done ---" >> "$RESULTS"
    echo "" >> "$RESULTS"
done

echo ""
echo "=== Sweep complete ==="
cat "$RESULTS"
