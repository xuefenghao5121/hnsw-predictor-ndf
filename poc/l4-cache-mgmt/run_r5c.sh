#!/bin/bash
# R5c: mincore diagnostic under 256MB cgroup
# Goal: understand page cache residency after search with WILLNEED_BG + PAGE_MERGE_BG
set -euo pipefail
cd /home/huawei/hnsw-predictor-ndf/poc/l4-cache-mgmt
BIN=build/benchmark_l4

GRAPH=../../output/sift1m_graph.bin
BFS=../../output/sift1m_bfs.bin
BLOCKS=../../output/sift1m_blocks_64k.bin
ROUTE=../../output/sift1m_route_64k.bin
DATA=../../data/sift_base.fvecs
QUERY=../../data/sift1m_query200.fvecs
GT=../../data/sift1m_gt200.bin
K=10; EF=100; NUMQ=200

CGROUP_MB=256
CGROUP_PATH=/sys/fs/cgroup/hnsw_l4_r5c

export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1
export VEC_BLOCKS_PATH=../../output/sift1m_vecblocks_64k.bin
export PQ_CODES_PATH=../../output/pqco_sift1m_M32_correct.bin
export REFINE_EF=100 FINE_PREAD=1 FINE_BUFFERED=1
export EVICT_PAGE_CACHE=0 NUM_THREADS=0
export L4_WILLNEED=1 WILLNEED_BG=1 VL_POOL_THREADS=14
export PAGE_MERGE_BG=1 FLAT_VEC_MB=64
export MINCORE_DIAG=1

echo "============================================"
echo "  R5c: mincore diagnostic (256MB cgroup)"
echo "============================================"

# Setup cgroup
sync
echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null
sudo mkdir -p "$CGROUP_PATH"
echo "$((CGROUP_MB * 1024 * 1024))" | sudo tee "$CGROUP_PATH/memory.max" > /dev/null

# Memory monitor
ML=/tmp/l4_r5c_mem.log
echo "" > "$ML"
( while true; do
    ts=$(date +%s%N)
    cur=$(cat "$CGROUP_PATH/memory.current" 2>/dev/null)
    anon=$(grep "^anon " "$CGROUP_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
    file=$(grep "^file " "$CGROUP_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
    echo "$ts $cur $anon $file" >> "$ML"
    sleep 0.1
done ) &
MP=$!

# Run benchmark in cgroup
sudo -E env PATH=$PATH \
    CACHE_MB=$CACHE_MB TWO_STAGE=$TWO_STAGE FINE_RERANK=$FINE_RERANK \
    VEC_BLOCKS_PATH=$VEC_BLOCKS_PATH PQ_CODES_PATH=$PQ_CODES_PATH \
    REFINE_EF=$REFINE_EF FINE_PREAD=$FINE_PREAD FINE_BUFFERED=$FINE_BUFFERED \
    EVICT_PAGE_CACHE=$EVICT_PAGE_CACHE NUM_THREADS=$NUM_THREADS \
    L4_WILLNEED=$L4_WILLNEED WILLNEED_BG=$WILLNEED_BG VL_POOL_THREADS=$VL_POOL_THREADS \
    PAGE_MERGE_BG=$PAGE_MERGE_BG FLAT_VEC_MB=$FLAT_VEC_MB \
    MINCORE_DIAG=$MINCORE_DIAG \
    bash -c "echo \$\$ > $CGROUP_PATH/cgroup.procs && $BIN \
    $GRAPH $BFS $BLOCKS $ROUTE $DATA $QUERY $GT $K $EF $NUMQ"

kill $MP 2>/dev/null || true

echo ""
echo "============================================"
echo "  R5c complete"
echo "============================================"
