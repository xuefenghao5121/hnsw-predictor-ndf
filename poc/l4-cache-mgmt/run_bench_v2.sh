#!/bin/bash
# run_l4_poc_v2.sh - L4 POC v2: 修正 PQ_CODES_PATH 后重跑
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

CGROUP_MB=512
CGROUP_PATH=/sys/fs/cgroup/hnsw_l4_v2

# FIXED: PQ_CODES_PATH (with S)
export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1
export VEC_BLOCKS_PATH=../../output/sift1m_vecblocks_64k.bin
export PQ_CODES_PATH=../../output/pqco_sift1m_M32_correct.bin
export REFINE_EF=100 FINE_PREAD=1 FINE_BUFFERED=1
export EVICT_PAGE_CACHE=0 NUM_THREADS=0
export PROFILE_TS=1

run_round() {
    local name=$1; shift
    echo ""; echo "============================================"
    echo "  $name"; echo "============================================"
    sync; echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null
    sudo mkdir -p "$CGROUP_PATH"
    echo "$((CGROUP_MB * 1024 * 1024))" | sudo tee "$CGROUP_PATH/memory.max" > /dev/null
    local ml="/tmp/l4v2_${name// /_}.log"; echo "" > "$ml"
    ( while true; do
        ts=$(date +%s%N); cur=$(cat "$CGROUP_PATH/memory.current" 2>/dev/null)
        anon=$(grep "^anon " "$CGROUP_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
        file=$(grep "^file " "$CGROUP_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
        echo "$ts $cur $anon $file" >> "$ml"; sleep 0.1
    done ) & local mp=$!
    echo $$ | sudo tee "$CGROUP_PATH/cgroup.procs" > /dev/null
    env "$@" $BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $EF $NUMQ 2>&1
    echo ""; echo "--- cgroup ---"
    echo "peak: $(cat $CGROUP_PATH/memory.peak) | events:"; cat "$CGROUP_PATH/memory.events"
    grep -E "^(anon|file|active_file|inactive_file|workingset_refault_file|pgmajfault)" "$CGROUP_PATH/memory.stat"
    echo "peaks: anon=$(awk '{if($3>m)m=$3}END{if(m>0)print m/1048576;else print 0}' "$ml")MB file=$(awk '{if($4>m)m=$4}END{if(m>0)print m/1048576;else print 0}' "$ml")MB total=$(awk '{if($2>m)m=$2}END{if(m>0)print m/1048576;else print 0}' "$ml")MB"
    kill $mp 2>/dev/null || true; wait $mp 2>/dev/null || true
    echo $$ | sudo tee /sys/fs/cgroup/cgroup.procs > /dev/null 2>/dev/null || true
    sudo rmdir "$CGROUP_PATH" 2>/dev/null || true
}

# R0: True Buffered (FINE_BUFFERED=1, no fadvise, no evict)
run_round "R0 Buffered" FINE_FADVISE=0 L4_EVICT_META=0

# R1: + FINE_FADVISE (evict vecblocks after read)
run_round "R1 +FADVISE" FINE_FADVISE=1 L4_EVICT_META=0

# R2: + L4_EVICT_META (evict graph+BFS after init)
run_round "R2 +EvictMeta" FINE_FADVISE=0 L4_EVICT_META=1

# R3: + both
run_round "R3 +Both" FINE_FADVISE=1 L4_EVICT_META=1
