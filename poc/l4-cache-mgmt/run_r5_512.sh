#!/bin/bash
# run_r5_512.sh - L4 POC R5: WILLNEED 512MB 回归验证
# 确认 WILLNEED 在 page cache 充裕场景下不回归
set -euo pipefail
cd /home/huawei/hnsw-predictor-ndf/poc/l4-cache-mgmt
BIN=build/benchmark_l4
DROP_CACHE=./drop_file_cache

GRAPH=../../output/sift1m_graph.bin
BFS=../../output/sift1m_bfs.bin
BLOCKS=../../output/sift1m_blocks_64k.bin
ROUTE=../../output/sift1m_route_64k.bin
DATA=../../data/sift_base.fvecs
QUERY=../../data/sift1m_query200.fvecs
GT=../../data/sift1m_gt200.bin
VECBLOCKS=../../output/sift1m_vecblocks_64k.bin
PQCODES=../../output/pqco_sift1m_M32_correct.bin
K=10; EF=100; NUMQ=200

CGROUP_MB=${1:-512}

EVICT_FILES="$GRAPH $BFS $BLOCKS $ROUTE $VECBLOCKS $PQCODES $DATA"

run_round() {
    local name=$1; shift
    local extra_env="$@"
    echo ""; echo "============================================"
    echo "  $name  (cgroup=${CGROUP_MB}MB)"
    echo "============================================"
    
    $DROP_CACHE $EVICT_FILES 2>/dev/null || true
    sync
    
    local unit_name="hnsw_r5_$(echo "$name" | tr -cd 'a-zA-Z0-9_')"
    
    systemd-run --scope --property=MemoryLimit=${CGROUP_MB}M \
        --unit="$unit_name" \
        --collect \
        bash -c "
            CG=/sys/fs/cgroup/system.slice/$unit_name.scope
            
            export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1
            export VEC_BLOCKS_PATH=$VECBLOCKS
            export PQ_CODES_PATH=$PQCODES
            export REFINE_EF=100 FINE_PREAD=1 FINE_BUFFERED=1
            export EVICT_PAGE_CACHE=0 NUM_THREADS=0 PROFILE_TS=1
            export $extra_env
            
            $BIN '$GRAPH' '$BFS' '$BLOCKS' '$ROUTE' '$DATA' '$QUERY' '$GT' $K $EF $NUMQ 2>&1
            
            echo ''
            echo '--- cgroup ---'
            echo \"peak: \$(cat \$CG/memory.peak 2>/dev/null)\"
            echo 'events:'
            cat \$CG/memory.events 2>/dev/null
            grep -E '^(anon|file|active_file|inactive_file|workingset_refault_file|pgmajfault)' \$CG/memory.stat 2>/dev/null
        " 2>&1 || true
}

# R5-512-base: Baseline (512MB, no WILLNEED)
run_round "R5-512-base" "FINE_FADVISE=0 L4_EVICT_META=1 L4_WILLNEED=0 L4_SELECTIVE_DONTNEED=0"

# R5-512-WILLNEED: +WILLNEED
run_round "R5-512-WILLNEED" "FINE_FADVISE=0 L4_EVICT_META=1 L4_WILLNEED=1 L4_SELECTIVE_DONTNEED=0"
