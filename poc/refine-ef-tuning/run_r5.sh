#!/bin/bash
# run_r5_refine_ef.sh - REFINE_EF R5: WILLNEED 下重扫 + PQ 联合
# CON-SLA-014: sudo drop_caches + sudo cgroup, DEEP10M 2GB
set -euo pipefail
cd /home/huawei/hnsw-predictor-ndf
BIN=build/benchmark_diskhnsw

GRAPH=output/deep10m_graph.bin
BFS=output/deep10m_bfs.bin
BLOCKS=output/deep10m_blocks_64k.bin
ROUTE=output/deep10m_route_64k.bin
DATA=data/deep10m_base.fvecs
QUERY=data/deep10m_query.fvecs
GT=data/deep10m_gt_k10.bin
VECBLOCKS=output/deep10m_vecblocks_64k.bin
PQ_M32=output/pqco_deep10m_M32.bin
PQ_M24=output/pqco_deep10m_M24.bin
K=10; NUMQ=200; CG_MB=2048

export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1
export VEC_BLOCKS_PATH=$VECBLOCKS
export FINE_PREAD=1 FINE_BUFFERED=1
export L4_EVICT_META=1 L4_WILLNEED=1
export NUM_THREADS=0 PROFILE_TS=1

run_round() {
    local name=$1; shift
    local ef=$1; shift
    local pq_path=$1; shift
    echo ""; echo "============================================"
    echo "  $name  (EF=$ef, cgroup=${CG_MB}MB, CON-SLA-014)"
    echo "============================================"
    sync; echo "huawei" | sudo -S sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null
    sudo mkdir -p /sys/fs/cgroup/hnsw_ref
    echo "$((CG_MB * 1024 * 1024))" | sudo tee /sys/fs/cgroup/hnsw_ref/memory.max > /dev/null
    echo $$ | sudo tee /sys/fs/cgroup/hnsw_ref/cgroup.procs > /dev/null
    export REFINE_EF=$ef
    export PQ_CODES_PATH=$pq_path
    $BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $ef $NUMQ 2>&1
    echo ""; echo "--- cgroup ---"
    echo "peak: $(cat /sys/fs/cgroup/hnsw_ref/memory.peak)"
    cat /sys/fs/cgroup/hnsw_ref/memory.events
    grep -E "^(anon|file|workingset_refault_file|pgmajfault)" /sys/fs/cgroup/hnsw_ref/memory.stat
    echo $$ | sudo tee /sys/fs/cgroup/cgroup.procs > /dev/null 2>/dev/null || true
    sudo rmdir /sys/fs/cgroup/hnsw_ref 2>/dev/null || true
}

# M=32 系列
run_round "R5-base-EF300-M32" 300 "$PQ_M32"
run_round "R5a-EF250-M32"     250 "$PQ_M32"
run_round "R5b-EF200-M32"     200 "$PQ_M32"

# M=24 系列
run_round "R5d-EF300-M24"     300 "$PQ_M24"
run_round "R5c-EF250-M24"     250 "$PQ_M24"
run_round "R5e-EF200-M24"     200 "$PQ_M24"
