#!/bin/bash
# run_r5_deep10m.sh - L4 POC R5 DEEP10M WILLNEED 验证 (CON-SLA-014)
set -euo pipefail
cd /home/huawei/hnsw-predictor-ndf/poc/l4-cache-mgmt
BIN=build/benchmark_l4

GRAPH=../../output/deep10m_graph.bin
BFS=../../output/deep10m_bfs.bin
BLOCKS=../../output/deep10m_blocks_64k.bin
ROUTE=../../output/deep10m_route_64k.bin
DATA=../../data/deep10m_base.fvecs
QUERY=../../data/deep10m_query.fvecs
GT=../../data/deep10m_gt_k10.bin
VECBLOCKS=../../output/deep10m_vecblocks_64k.bin
PQCODES=../../output/pqco_deep10m_M32.bin
K=10; EF=100; NUMQ=200

export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1
export VEC_BLOCKS_PATH=$VECBLOCKS
export PQ_CODES_PATH=$PQCODES
export REFINE_EF=300 FINE_PREAD=1 FINE_BUFFERED=1
export EVICT_PAGE_CACHE=0 NUM_THREADS=0 PROFILE_TS=1

CGROUP_MB=${1:-2048}

run_round() {
    local name=$1; shift
    echo ""; echo "============================================"
    echo "  $name  (cgroup=${CGROUP_MB}MB, DEEP10M, CON-SLA-014)"
    echo "============================================"
    sync; echo "huawei" | sudo -S sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null
    sudo mkdir -p /sys/fs/cgroup/hnsw_r5_deep
    echo "$((CGROUP_MB * 1024 * 1024))" | sudo tee /sys/fs/cgroup/hnsw_r5_deep/memory.max > /dev/null
    local ml="/tmp/l4r5deep_${name// /_}.log"; echo "" > "$ml"
    ( while true; do
        ts=$(date +%s%N); cur=$(cat /sys/fs/cgroup/hnsw_r5_deep/memory.current 2>/dev/null)
        anon=$(grep "^anon " /sys/fs/cgroup/hnsw_r5_deep/memory.stat 2>/dev/null | awk '{print $2}')
        file=$(grep "^file " /sys/fs/cgroup/hnsw_r5_deep/memory.stat 2>/dev/null | awk '{print $2}')
        echo "$ts $cur $anon $file" >> "$ml"; sleep 0.1
    done ) & local mp=$!
    echo $$ | sudo tee /sys/fs/cgroup/hnsw_r5_deep/cgroup.procs > /dev/null
    env "$@" $BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $EF $NUMQ 2>&1
    echo ""; echo "--- cgroup (CON-SLA-014) ---"
    echo "peak: $(cat /sys/fs/cgroup/hnsw_r5_deep/memory.peak)"
    echo "events:"; cat /sys/fs/cgroup/hnsw_r5_deep/memory.events
    grep -E "^(anon|file|active_file|inactive_file|workingset_refault_file|pgmajfault)" /sys/fs/cgroup/hnsw_r5_deep/memory.stat
    echo "peaks: anon=$(awk '{if($3>m)m=$3}END{if(m>0)print m/1048576;else print 0}' "$ml")MB file=$(awk '{if($4>m)m=$4}END{if(m>0)print m/1048576;else print 0}' "$ml")MB total=$(awk '{if($2>m)m=$2}END{if(m>0)print m/1048576;else print 0}' "$ml")MB"
    kill $mp 2>/dev/null || true; wait $mp 2>/dev/null || true
    echo $$ | sudo tee /sys/fs/cgroup/cgroup.procs > /dev/null 2>/dev/null || true
    sudo rmdir /sys/fs/cgroup/hnsw_r5_deep 2>/dev/null || true
}

# DEEP10M 2GB baseline (no WILLNEED)
run_round "DEEP10M-2G-base" L4_EVICT_META=1 L4_WILLNEED=0 L4_SELECTIVE_DONTNEED=0

# DEEP10M 2GB + WILLNEED
run_round "DEEP10M-2G-WILLNEED" L4_EVICT_META=1 L4_WILLNEED=1 L4_SELECTIVE_DONTNEED=0
