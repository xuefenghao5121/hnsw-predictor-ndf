#!/bin/bash
# run_opq.sh - PQ quality: OPQ M=24 vs PQ M=24 vs PQ M=32
# CON-SLA-014, DEEP10M 2GB, WILLNEED=1
set -euo pipefail
cd /home/huawei/hnsw-predictor-ndf
BIN=build/benchmark_diskhnsw

GRAPH=output/deep10m_graph.bin
BFS=output/deep10m_bfs.bin
BLOCKS=output/deep10m_blocks_64k.bin
ROUTE=output/deep10m_route_64k.bin
DATA=data/deep10m_base.fvecs
GT=data/deep10m_gt_k10.bin
VECBLOCKS=output/deep10m_vecblocks_64k.bin
K=10; NUMQ=200; CG_MB=2048

export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1
export VEC_BLOCKS_PATH=$VECBLOCKS
export REFINE_EF=300 FINE_PREAD=1 FINE_BUFFERED=1
export L4_EVICT_META=1 L4_WILLNEED=1
export NUM_THREADS=0 PROFILE_TS=1

run_round() {
    local name=$1; shift
    local pq=$1; shift
    local query=$1; shift
    local ef=${1:-300}; shift 2>/dev/null || true
    echo ""; echo "============================================"
    echo "  $name  (EF=$ef, cgroup=${CG_MB}MB, CON-SLA-014)"
    echo "============================================"
    sync; echo "huawei" | sudo -S sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null
    sudo mkdir -p /sys/fs/cgroup/hnsw_pq
    echo "$((CG_MB * 1024 * 1024))" | sudo tee /sys/fs/cgroup/hnsw_pq/memory.max > /dev/null
    echo $$ | sudo tee /sys/fs/cgroup/hnsw_pq/cgroup.procs > /dev/null
    export REFINE_EF=$ef PQ_CODES_PATH=$pq
    $BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$query" "$GT" $K $ef $NUMQ 2>&1
    echo ""; echo "--- cgroup ---"
    cat /sys/fs/cgroup/hnsw_pq/memory.events
    grep -E "^(anon|file|workingset_refault_file|pgmajfault)" /sys/fs/cgroup/hnsw_pq/memory.stat
    echo $$ | sudo tee /sys/fs/cgroup/cgroup.procs > /dev/null 2>/dev/null || true
    sudo rmdir /sys/fs/cgroup/hnsw_pq 2>/dev/null || true
}

# OPQ M=24 (旋转 query) EF=300
run_round "OPQ-M24-EF300" output/pqco_deep10m_opq_m24.bin data/deep10m_query_opq_m24.fvecs 300

# OPQ M=24 EF=250
run_round "OPQ-M24-EF250" output/pqco_deep10m_opq_m24.bin data/deep10m_query_opq_m24.fvecs 250

# PQ M=32 (原始 query) EF=300 - 基线对照
run_round "PQ-M32-EF300-base" output/pqco_deep10m_M32.bin data/deep10m_query.fvecs 300

# OPQ M=32 (旋转 query) EF=300 - 对比 OPQ 效果
run_round "OPQ-M32-EF300" output/pqco_deep10m_opq_m32.bin data/deep10m_query_opq.fvecs 300
