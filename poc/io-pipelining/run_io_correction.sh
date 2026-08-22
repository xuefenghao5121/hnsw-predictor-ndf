#!/bin/bash
# run_io_correction.sh - I/O behavior correction Phase 1+3 (CON-SLA-014)
# DEEP10M @ 2GB: R0 (PIPE_FINE=0) vs R1 (PIPE_FINE=1)
# SIFT1M @ 512MB: R0 vs R1 烟测
set -euo pipefail
cd /home/huawei/hnsw-predictor-ndf/poc/io-pipelining
BIN=build/benchmark_pipe

GRAPH=../../output/deep10m_graph.bin
BFS=../../output/deep10m_bfs.bin
BLOCKS=../../output/deep10m_blocks_64k.bin
ROUTE=../../output/deep10m_route_64k.bin
DATA=../../data/deep10m_base.fvecs
QUERY=../../data/deep10m_query.fvecs
GT=../../data/deep10m_gt_k10.bin
VECBLOCKS=../../output/deep10m_vecblocks_64k.bin
PQCODES=../../output/pqco_deep10m_M32.bin
K=10; EF=300; NUMQ=200

run_round() {
    local name=$1; shift
    local cg_mb=$1; shift
    local dataset=$1; shift
    echo ""; echo "============================================"
    echo "  $name  ($dataset, cgroup=${cg_mb}MB, CON-SLA-014)"
    echo "============================================"
    sync; echo "huawei" | sudo -S sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null
    sudo mkdir -p /sys/fs/cgroup/hnsw_io_corr
    echo "$((cg_mb * 1024 * 1024))" | sudo tee /sys/fs/cgroup/hnsw_io_corr/memory.max > /dev/null
    local ml="/tmp/io_corr_${name// /_}.log"; echo "" > "$ml"
    ( while true; do
        ts=$(date +%s%N); cur=$(cat /sys/fs/cgroup/hnsw_io_corr/memory.current 2>/dev/null)
        anon=$(grep "^anon " /sys/fs/cgroup/hnsw_io_corr/memory.stat 2>/dev/null | awk '{print $2}')
        file=$(grep "^file " /sys/fs/cgroup/hnsw_io_corr/memory.stat 2>/dev/null | awk '{print $2}')
        echo "$ts $cur $anon $file" >> "$ml"; sleep 0.1
    done ) & local mp=$!
    echo $$ | sudo tee /sys/fs/cgroup/hnsw_io_corr/cgroup.procs > /dev/null
    env "$@" $BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $EF $NUMQ 2>&1
    echo ""; echo "--- cgroup (CON-SLA-014) ---"
    echo "peak: $(cat /sys/fs/cgroup/hnsw_io_corr/memory.peak)"
    echo "events:"; cat /sys/fs/cgroup/hnsw_io_corr/memory.events
    grep -E "^(anon|file|workingset_refault_file|pgmajfault)" /sys/fs/cgroup/hnsw_io_corr/memory.stat
    echo "peaks: anon=$(awk '{if($3>m)m=$3}END{if(m>0)print m/1048576;else print 0}' "$ml")MB file=$(awk '{if($4>m)m=$4}END{if(m>0)print m/1048576;else print 0}' "$ml")MB"
    kill $mp 2>/dev/null || true; wait $mp 2>/dev/null || true
    echo $$ | sudo tee /sys/fs/cgroup/cgroup.procs > /dev/null 2>/dev/null || true
    sudo rmdir /sys/fs/cgroup/hnsw_io_corr 2>/dev/null || true
}

export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1
export VEC_BLOCKS_PATH=$VECBLOCKS PQ_CODES_PATH=$PQCODES
export REFINE_EF=300 FINE_PREAD=1 FINE_BUFFERED=1
export NUM_THREADS=0 PROFILE_TS=1
export L4_EVICT_META=1 L4_WILLNEED=1

# Phase 1+3: DEEP10M @ 2GB
run_round "DEEP10M-2G-R0-base" 2048 DEEP10M PIPE_FINE=0
run_round "DEEP10M-2G-R1-pipe" 2048 DEEP10M PIPE_FINE=1

# Phase 1+3: DEEP10M @ 3GB (宽松预算对照)
run_round "DEEP10M-3G-R0-base" 3072 DEEP10M PIPE_FINE=0
run_round "DEEP10M-3G-R1-pipe" 3072 DEEP10M PIPE_FINE=1
