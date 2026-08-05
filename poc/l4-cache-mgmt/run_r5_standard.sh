#!/bin/bash
# run_r5_standard.sh - L4 POC R5 标准协议重跑 (CON-SLA-014)
# 使用 sudo echo 3 > drop_caches + sudo cgroup (非 systemd-run)
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

export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1
export VEC_BLOCKS_PATH=../../output/sift1m_vecblocks_64k.bin
export PQ_CODES_PATH=../../output/pqco_sift1m_M32_correct.bin
export REFINE_EF=100 FINE_PREAD=1 FINE_BUFFERED=1
export EVICT_PAGE_CACHE=0 NUM_THREADS=0 PROFILE_TS=1

run_round() {
    local name=$1; shift
    local cg_mb=$1; shift
    echo ""; echo "============================================"
    echo "  $name  (cgroup=${cg_mb}MB, CON-SLA-014)"
    echo "============================================"
    sync; echo "huawei" | sudo -S sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null
    sudo mkdir -p /sys/fs/cgroup/hnsw_r5_std
    echo "$((cg_mb * 1024 * 1024))" | sudo tee /sys/fs/cgroup/hnsw_r5_std/memory.max > /dev/null
    local ml="/tmp/l4r5std_${name// /_}.log"; echo "" > "$ml"
    ( while true; do
        ts=$(date +%s%N); cur=$(cat /sys/fs/cgroup/hnsw_r5_std/memory.current 2>/dev/null)
        anon=$(grep "^anon " /sys/fs/cgroup/hnsw_r5_std/memory.stat 2>/dev/null | awk '{print $2}')
        file=$(grep "^file " /sys/fs/cgroup/hnsw_r5_std/memory.stat 2>/dev/null | awk '{print $2}')
        echo "$ts $cur $anon $file" >> "$ml"; sleep 0.1
    done ) & local mp=$!
    echo $$ | sudo tee /sys/fs/cgroup/hnsw_r5_std/cgroup.procs > /dev/null
    env "$@" $BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $EF $NUMQ 2>&1
    echo ""; echo "--- cgroup (CON-SLA-014) ---"
    echo "peak: $(cat /sys/fs/cgroup/hnsw_r5_std/memory.peak)"
    echo "events:"; cat /sys/fs/cgroup/hnsw_r5_std/memory.events
    grep -E "^(anon|file|active_file|inactive_file|workingset_refault_file|pgmajfault)" /sys/fs/cgroup/hnsw_r5_std/memory.stat
    echo "peaks: anon=$(awk '{if($3>m)m=$3}END{if(m>0)print m/1048576;else print 0}' "$ml")MB file=$(awk '{if($4>m)m=$4}END{if(m>0)print m/1048576;else print 0}' "$ml")MB total=$(awk '{if($2>m)m=$2}END{if(m>0)print m/1048576;else print 0}' "$ml")MB"
    kill $mp 2>/dev/null || true; wait $mp 2>/dev/null || true
    echo $$ | sudo tee /sys/fs/cgroup/cgroup.procs > /dev/null 2>/dev/null || true
    sudo rmdir /sys/fs/cgroup/hnsw_r5_std 2>/dev/null || true
}

# 256MB: 基线 vs WILLNEED
run_round "R5-256-base" 256 FINE_FADVISE=0 L4_EVICT_META=1 L4_WILLNEED=0 L4_SELECTIVE_DONTNEED=0
run_round "R5-256-WILLNEED" 256 FINE_FADVISE=0 L4_EVICT_META=1 L4_WILLNEED=1 L4_SELECTIVE_DONTNEED=0

# 512MB: 基线 vs WILLNEED (回归验证)
run_round "R5-512-base" 512 FINE_FADVISE=0 L4_EVICT_META=1 L4_WILLNEED=0 L4_SELECTIVE_DONTNEED=0
run_round "R5-512-WILLNEED" 512 FINE_FADVISE=0 L4_EVICT_META=1 L4_WILLNEED=1 L4_SELECTIVE_DONTNEED=0
