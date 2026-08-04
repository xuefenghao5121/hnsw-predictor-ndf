#!/bin/bash
# run_trunk_perf.sh - Trunk 性能验证 (CON-SLA-014, 场景6)
# 验证 WILLNEED 合入 src/ 后: WILLNEED=0 无回归, WILLNEED=1 有效
set -euo pipefail
cd /home/huawei/hnsw-predictor-ndf
BIN=build/benchmark_diskhnsw

GRAPH=output/sift1m_graph.bin
BFS=output/sift1m_bfs.bin
BLOCKS=output/sift1m_blocks_64k.bin
ROUTE=output/sift1m_route_64k.bin
DATA=data/sift_base.fvecs
QUERY=data/sift1m_query200.fvecs
GT=data/sift1m_gt200.bin
K=10; EF=100; NUMQ=200

export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1
export VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin
export PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin
export REFINE_EF=100 FINE_PREAD=1 FINE_BUFFERED=1
export EVICT_PAGE_CACHE=0 NUM_THREADS=0 PROFILE_TS=1

run_round() {
    local name=$1; shift
    local cg_mb=$1; shift
    echo ""; echo "============================================"
    echo "  $name  (cgroup=${cg_mb}MB, Trunk, CON-SLA-014)"
    echo "============================================"
    sync; echo "huawei" | sudo -S sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null
    sudo mkdir -p /sys/fs/cgroup/hnsw_trunk_perf
    echo "$((cg_mb * 1024 * 1024))" | sudo tee /sys/fs/cgroup/hnsw_trunk_perf/memory.max > /dev/null
    local ml="/tmp/trunk_perf_${name// /_}.log"; echo "" > "$ml"
    ( while true; do
        ts=$(date +%s%N); cur=$(cat /sys/fs/cgroup/hnsw_trunk_perf/memory.current 2>/dev/null)
        anon=$(grep "^anon " /sys/fs/cgroup/hnsw_trunk_perf/memory.stat 2>/dev/null | awk '{print $2}')
        file=$(grep "^file " /sys/fs/cgroup/hnsw_trunk_perf/memory.stat 2>/dev/null | awk '{print $2}')
        echo "$ts $cur $anon $file" >> "$ml"; sleep 0.1
    done ) & local mp=$!
    echo $$ | sudo tee /sys/fs/cgroup/hnsw_trunk_perf/cgroup.procs > /dev/null
    env "$@" $BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $EF $NUMQ 2>&1
    echo ""; echo "--- cgroup (CON-SLA-014) ---"
    echo "peak: $(cat /sys/fs/cgroup/hnsw_trunk_perf/memory.peak)"
    echo "events:"; cat /sys/fs/cgroup/hnsw_trunk_perf/memory.events
    grep -E "^(anon|file|workingset_refault_file|pgmajfault)" /sys/fs/cgroup/hnsw_trunk_perf/memory.stat
    kill $mp 2>/dev/null || true; wait $mp 2>/dev/null || true
    echo $$ | sudo tee /sys/fs/cgroup/cgroup.procs > /dev/null 2>/dev/null || true
    sudo rmdir /sys/fs/cgroup/hnsw_trunk_perf 2>/dev/null || true
}

# 512MB: WILLNEED=0 (无回归验证)
run_round "Trunk-512-WILLNEED0" 512 L4_EVICT_META=1 L4_WILLNEED=0

# 512MB: WILLNEED=1 (有效验证)
run_round "Trunk-512-WILLNEED1" 512 L4_EVICT_META=1 L4_WILLNEED=1

# 256MB: WILLNEED=0 (基线)
run_round "Trunk-256-WILLNEED0" 256 L4_EVICT_META=1 L4_WILLNEED=0

# 256MB: WILLNEED=1 (17.7x 验证)
run_round "Trunk-256-WILLNEED1" 256 L4_EVICT_META=1 L4_WILLNEED=1
